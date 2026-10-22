import io
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import numpy as np
import pytest
from docx import Document
from app.case_data import parse_zip,check_snapshot,FEATURES
from app.signal_data import analyse,features
from app.rules import evaluate
from app.knowledge import import_knowledge,retrieve
from app.writer import prepare_context,write_report,validate_evidence_claims
from scripts.generate_samples import build,make_case


@pytest.fixture(scope='module')
def samples(tmp_path_factory):
    dest=tmp_path_factory.mktemp('samples');build(dest);return dest


def read_sample(samples,name):
    s=parse_zip((samples/f'{name}.zip').read_bytes());s['quality']=check_snapshot(s);return s


def mutate(raw,change):
    with ZipFile(io.BytesIO(raw)) as z:data={i.filename:z.read(i) for i in z.infolist()}
    change(data)
    stream=io.BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for k,v in data.items():z.writestr(k,v)
    return stream.getvalue()


@pytest.mark.parametrize('kind',['stable','rising','impulse','missing'])
def test_case_consistency(samples,kind):
    s=read_sample(samples,kind);a=analyse(s)
    assert not a['warnings']
    case,h,w=make_case(kind)
    for k in FEATURES:
        assert s['current_features'][k]==pytest.approx(features(w,case['sampling_rate'])[k])
    if kind=='missing':
        assert a['features']['velocity_rms'] is not None
        assert not a['frequency'] and not a['rpm_available']
    else:
        assert all(r['status']=='一致' for r in a['comparisons'])
    if kind=='impulse':assert a['features']['kurtosis']>10 and a['features']['crest_factor']>4


@pytest.mark.parametrize('field,value',[('sampling_rate',0),('sample_count',12799),('duration_seconds',10),('unit','g'),('simulated',False)])
def test_invalid_metadata(samples,field,value):
    s=read_sample(samples,'rising');s[field]=value
    with pytest.raises(ValueError):check_snapshot(s)


def test_missing_fields_and_bad_identity(samples):
    s=read_sample(samples,'rising');del s['device']['model']
    with pytest.raises(ValueError,match='model'):check_snapshot(s)
    s=read_sample(samples,'rising');s['history'][0]['point_id']='other'
    with pytest.raises(ValueError,match='不对应'):check_snapshot(s)


def test_time_point_count_and_spacing(samples):
    s=read_sample(samples,'stable');s['current_features']['measured_time']='2026-10-23T12:00:00'
    with pytest.raises(ValueError,match='时间必须'):check_snapshot(s)
    s=read_sample(samples,'stable');s['waveform'].pop()
    with pytest.raises(ValueError,match='点数'):check_snapshot(s)
    s=read_sample(samples,'stable');s['waveform_times'][10]+=.1
    with pytest.raises(ValueError,match='步长'):check_snapshot(s)


def test_feature_mismatch_is_visible(samples):
    s=read_sample(samples,'rising');s['current_features']['velocity_rms']*=2
    s['quality']=check_snapshot(s);a=analyse(s)
    assert a['warnings'] and any(r['status'].startswith('不一致') for r in a['comparisons'])
    assert a['features']['velocity_rms']==pytest.approx(s['history'][-1]['velocity_rms'])
    assert a['uploaded_features']['velocity_rms']==pytest.approx(2*a['features']['velocity_rms'])


def test_missing_rpm_alone_keeps_spectrum(samples):
    s=read_sample(samples,'stable');s['device']['rpm']=None;s['quality']=check_snapshot(s)
    a=analyse(s);assert a['peaks'] and not a['rpm_available']


def test_no_waveform_does_not_create_features(samples):
    s=read_sample(samples,'missing');s['current_features']['kurtosis']=None;s['history'][-1]['kurtosis']=None
    s['quality']=check_snapshot(s);a=analyse(s)
    assert a['features']['kurtosis'] is None and a['recomputed_features']=={}
    assert not a['peaks'] and a['features']['velocity_rms'] is not None


def test_unsafe_zip_rejected(samples):
    raw=mutate((samples/'stable.zip').read_bytes(),lambda d:d.update({'../attack.txt':b'x'}))
    with pytest.raises(ValueError,match='根目录'):parse_zip(raw)


def test_nonfinite_rejected(samples):
    raw=mutate((samples/'stable.zip').read_bytes(),lambda d:d.update({'waveform.csv':d['waveform.csv'].replace(b'0.0,',b'NaN,',1)}))
    with pytest.raises(ValueError,match='NaN'):parse_zip(raw)


def test_full_knowledge_and_source(tmp_path):
    d=Document()
    for cat in ['电动机','风机']:
        d.add_heading(cat,1)
        for i in range(6):
            d.add_heading(f'故障{i}',2)
            for text in ['机理现象：典型振动','机理原因：可能原因','解决措施：复查','机理规则：不得自动执行']:
                d.add_paragraph(text)
    source=tmp_path/'test.docx';d.save(source)
    records=import_knowledge(source,tmp_path/'knowledge.json','原始资料.docx')
    assert len(retrieve(records))==12
    assert all(r['source']=='原始资料.docx' and r['category'] and r['fault'] and r['section'] for r in records)
    assert records[-1]['rule_text']=='不得自动执行'


def test_context_overflow_does_not_fallback_or_truncate(monkeypatch):
    monkeypatch.setenv('MODEL_CONTEXT_TOKENS','5000')
    k=[{'id':'KB-999','phenomena':'完整内容'*5000}]
    with pytest.raises(ValueError,match='未截断知识'):write_report({},k,False)


def test_all_input_preserved_in_context():
    facts={'device':{'model':'example'},'uploaded_current_features':{'velocity_rms':2.2},'spectrum_peaks':[25]}
    knowledge=[{'id':f'KB-{i}','phenomena':'原文'} for i in range(16)]
    text,budget=prepare_context(facts,knowledge)
    assert json.loads(text)=={'facts':facts,'knowledge':knowledge}
    assert budget['knowledge_count']==16


def test_model_cannot_deny_available_waveform():
    data={'mechanism':'周期激励需复核','limitations':'本次未提供可查看的原始波形','action1':'核查安装状态','action2':'补测温度信息'}
    with pytest.raises(ValueError,match='已提供原始波形'):
        validate_evidence_claims(data,{'availability':{'raw_waveform_provided':True}})


def test_unknown_trend_is_not_reported_as_below_threshold(samples):
    s=read_sample(samples,'missing')
    s['history']=s['history'][-1:]
    d=evaluate(s,analyse(s),[{'id':'D','kind':'demo_trend','name':'演示','source':'演示','enabled':True,'threshold_percent':30}])
    assert d['change_percent'] is None and '资料不足' in d['state']
