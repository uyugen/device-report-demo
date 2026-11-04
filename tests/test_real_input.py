import csv
import hashlib
import io
import json
from copy import deepcopy
from zipfile import ZIP_DEFLATED, ZipFile
import pytest
from app.case_data import parse_zip, check_snapshot
from app.signal_data import analyse
from app.rules import evaluate
from app.writer import prepare_context, validate_real_narrative, validate_evidence_claims


def real_zip(change=None):
    data={}
    ds=[]
    for index,kind,code,unit,rows in [
        (1,'trend','velocity_rms','mm/s',[['2','2026-10-20 18:00:00','0.10'],['3','2026-10-26 17:00:00','12.345678901234567']]),
        (2,'waveform',None,'m/s²',[['2','0','0.1'],['3','0.001','-0.1']]),
        (3,'spectrum',None,'m/s²',[['2','50','5.432109876543210'],['3','100','0.02765432109876543']])]:
        path=f'data/data{index}.csv';stream=io.StringIO(newline='');w=csv.writer(stream)
        w.writerow(['source_row','x','y']);w.writerows(rows);data[path]=stream.getvalue().encode()
        ds.append({'dataset_id':f'DS-{index:02d}','name':code or kind,'kind':kind,'feature_code':code,
                   'device_id':'DEVICE','point_ref':'POINT','source_id':f'SRC-{index}',
                   'data_file':path,'data_sha256':hashlib.sha256(data[path]).hexdigest(),'row_count':len(rows),
                   'x_axis':{'unit':None if kind=='trend' else 's' if kind=='waveform' else 'Hz'},
                   'y_axis':{'unit':unit},'acquisition':{'measured_time':None},'sampling':None})
    c={'schema_version':'1.1','case_id':'REAL-TEST','case_name':'测试数据，仅用于自动化验证',
       'data_type':'real_measurement','device':{'device_id':'DEVICE','device_name':'测试设备','device_type':'电动机','location':'测试','installation_date':'2026-10-21'},
       'point':{'local_point_id':'POINT','name_raw':'PZ','component_raw':'电机端','direction_code_raw':'Z'},
       'operating_condition':{'rpm':3000,'rotational_frequency_hz':50},
       'latest_acquisition':{'dataset_ids':['DS-02','DS-03'],'measured_time':None},
       'current_features':None,'datasets':ds,'charts':[{'chart_id':'CH'+str(i),'dataset_id':d['dataset_id']} for i,d in enumerate(ds)],
       'sources':[{'source_id':d['source_id'],'path':d['data_file'],'sha256':d['data_sha256']} for d in ds],
       'limitations':[]}
    if change:change(c,data)
    data['case.json']=json.dumps(c,ensure_ascii=False).encode()
    out=io.BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for name,raw in data.items():z.writestr(name,raw)
    return out.getvalue()


def read(raw=None):
    s=parse_zip(raw or real_zip());s['quality']=check_snapshot(s);return s


def test_derived_test_requires_notice_and_preserves_final_value_processing():
    def missing(c,data):c['data_type']='derived_test'
    with pytest.raises(ValueError,match='data_notice'):read(real_zip(missing))
    def marked(c,data):
        c['data_type']='derived_test';c['data_notice']='故障注入测试数据，不代表客户真实故障。'
    s=read(real_zip(marked));a=analyse(s)
    assert s['is_test_data'] and '测试' in s['data_notice']
    assert not a['signal_recalculation'] and not a['recomputed_features']
    assert not read()['is_test_data']


def test_real_final_values_are_never_recomputed(monkeypatch):
    def fail(*args,**kwargs):raise AssertionError('不得调用信号复算')
    monkeypatch.setattr('app.signal_data.features',fail)
    monkeypatch.setattr('app.signal_data.np.fft.rfft',fail)
    s=read();a=analyse(s)
    assert s['mode']=='real_measurement' and s['measured_time'] is None
    assert s['current_features']=={} and a['features']=={} and a['recomputed_features']=={}
    assert a['series'][0]['last']['y']=='12.345678901234567'
    assert a['order_coordinates'][0]['amplitude']=='5.432109876543210'
    assert a['order_coordinates'][2]['amplitude'] is None
    assert a['order_coordinates'][0]['method']=='exact_coordinate_lookup'
    assert not a['signal_recalculation'] and not a['history_linked_to_latest']
    assert a['warnings'] and not a['peaks']


@pytest.mark.parametrize('change,match',[
    (lambda c,d:c['datasets'][0]['y_axis'].update(unit='g'),'单位'),
    (lambda c,d:c['datasets'][0].update(device_id='OTHER'),'不对应'),
    (lambda c,d:d.update({'data/data1.csv':b'changed'}),'校验值'),
    (lambda c,d:c['operating_condition'].update(rotational_frequency_hz=60),'转速与转频'),
    (lambda c,d:d.update({'../escape.py':b'bad'}),'不安全'),
    (lambda c,d:d.update({'extra.py':b'bad'}),'其他附件'),
    (lambda c,d:c['datasets'][1].update(sampling={'sample_count':3}),'点数'),
    (lambda c,d:c['datasets'][1].update(sampling={'sampling_rate_hz':500}),'时间步长'),
    (lambda c,d:c.update(current_features={'velocity_rms':2}),'current_features'),
])
def test_real_bad_inputs_are_rejected(change,match):
    with pytest.raises(ValueError,match=match):read(real_zip(change))


def test_missing_waveform_still_allows_provided_spectrum():
    def change(c,data):
        d=c['datasets'].pop(1);del data[d['data_file']]
        c['sources']=[v for v in c['sources'] if v['source_id']!=d['source_id']]
        c['charts']=[v for v in c['charts'] if v['dataset_id']!=d['dataset_id']]
        c['latest_acquisition']['dataset_ids']=['DS-03']
    s=read(real_zip(change));a=analyse(s)
    assert s['waveform'] is None and a['spectrum_provided'] and a['order_coordinates']


def test_demo_threshold_is_never_applied_to_real_data():
    s=read();a=analyse(s)
    d=evaluate(s,a,[{'id':'DEMO','kind':'demo_trend','name':'测试','enabled':True,'source':'测试','threshold_percent':1}])
    assert d['change_percent'] is None and d['rules'][0]['status']=='不适用'
    assert d['fault']=='未定位' and d['severity']=='未分级'


def test_hypotheses_require_real_evidence_and_knowledge():
    s=read();a=analyse(s)
    facts={'mode':'real_measurement','evidence_items':a['evidence_items'],'availability':{'raw_waveform_provided':True,'spectrum_provided':True}}
    h={'fault':'转子不平衡','assessment':'待核查','explanation':'倍频坐标可作为排查线索，尚需同工况证据核实。',
       'supporting_evidence':['EV-ORDER-1'],'conflicting_evidence':[],
       'missing_evidence':['缺少同物理量的幅值比及关联工况'],'knowledge_ids':['KB-001']}
    text={'mechanism':'已有资料可作为故障排查线索。','limitations':'当前尚缺采集关联及指标口径。',
          'action1':'建议核对工况并检查测点安装。','action2':'建议同工况复测后进一步核实。','citations':['KB-001'],'hypotheses':[h]}
    assert validate_real_narrative(text,['KB-001'],facts)['hypotheses']
    broken=deepcopy(text);broken['hypotheses'][0]['supporting_evidence']=['MADE-UP']
    with pytest.raises(ValueError,match='不存在'):validate_real_narrative(broken,['KB-001'],facts)
    broken=deepcopy(text);broken['hypotheses'][0]['explanation']='波形显示周期冲击，确定为故障。'
    with pytest.raises(ValueError):validate_real_narrative(broken,['KB-001'],facts)


def test_full_context_over_limit_is_not_truncated(monkeypatch):
    monkeypatch.setenv('MODEL_CONTEXT_TOKENS','100')
    with pytest.raises(ValueError,match='未截断'):prepare_context({'mode':'real_measurement'},[{'id':'KB','text':'原文'*300}])


def test_independent_spectrum_availability():
    t={'mechanism':'已有频谱可用于查找对应坐标','limitations':'缺少当前绝对采集时间','action1':'需要进一步核查采集条件','action2':'建议补充同工况记录'}
    assert validate_evidence_claims(t,{'mode':'real_measurement','availability':{'raw_waveform_provided':False,'spectrum_provided':True}})


@pytest.mark.parametrize('limitation',[
    '缺少波形采样参数，需核对采集关联。',
    '未提供原始波形的绝对采集时间。',
    '缺少频谱幅值口径及采集工况。',
    '未提供频谱的采集关联信息。',
])
def test_signal_metadata_gaps_do_not_mean_missing_signal(limitation):
    t={'mechanism':'选定倍频坐标可供核查。','limitations':limitation,
       'action1':'建议核对现场采集条件。','action2':'建议补齐指标口径记录。'}
    assert validate_evidence_claims(t,{'mode':'real_measurement','availability':{
        'raw_waveform_provided':True,'spectrum_provided':True}})


@pytest.mark.parametrize('limitation',[
    '未提供原始波形，需要补充。','缺少当前频谱，需要补测。',
    '缺少波形采样参数，且未提供时域波形。',
])
def test_false_missing_signal_claims_still_rejected(limitation):
    t={'mechanism':'选定倍频坐标可供核查。','limitations':limitation,
       'action1':'建议核对现场采集条件。','action2':'建议补齐指标口径记录。'}
    with pytest.raises(ValueError,match='不能声称'):
        validate_evidence_claims(t,{'mode':'real_measurement','availability':{
            'raw_waveform_provided':True,'spectrum_provided':True}})


def test_model_contract_with_fake_transport_only(monkeypatch):
    # No request leaves the process; validates the actual writer wrapper and fallback.
    from app.writer import write_report
    from app.real_data import real_facts,real_decision
    s=read();a=analyse(s);facts=real_facts(s,a,real_decision(s,a,[]))
    text={'mechanism':'选定倍频坐标可作为排查线索。','limitations':'目前缺少同次采集关联及幅值口径。',
          'action1':'建议核查工况并进行现场检查。','action2':'建议补齐证据后复核相关机理。','citations':['KB-001'],
          'hypotheses':[{'fault':'转子不平衡','assessment':'待核查','explanation':'已有倍频坐标可作为待核实线索。',
                         'supporting_evidence':['EV-ORDER-1'],'conflicting_evidence':[],
                         'missing_evidence':['缺少同物理量幅值比'],'knowledge_ids':['KB-001']}]}
    class FakeResponse:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':json.dumps(text)}}]}
    class FakeClient:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            assert url=='https://unit-test.invalid/v1/chat/completions'
            assert json.loads(kwargs['json']['messages'][1]['content'])['facts']['mode']=='real_measurement'
            return FakeResponse()
    monkeypatch.setenv('LLM_ENABLED','true');monkeypatch.setenv('MODEL_API_KEY','test-only')
    monkeypatch.setenv('MODEL_BASE_URL','https://unit-test.invalid')
    monkeypatch.setattr('app.writer.httpx.Client',FakeClient)
    output,info=write_report(facts,[{'id':'KB-001','fault':'转子不平衡'}],True)
    assert info['mode']=='llm' and output['hypotheses'][0]['supporting_evidence']==['EV-ORDER-1']
    text['hypotheses'][0]['supporting_evidence']=['FAKE']
    output,info=write_report(facts,[{'id':'KB-001','fault':'转子不平衡'}],True)
    assert info['mode']=='template' and output['hypotheses']==[] and '未通过' in info['message']
