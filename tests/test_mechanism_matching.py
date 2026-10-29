import csv
import json
from copy import deepcopy
from pathlib import Path
import pytest
from app.mechanism_rules import match_rules, run_condition, support, write_matches_csv
from app.rules import validate_rules
from app.real_data import real_facts
from app.writer import prepare_context, validate_real_narrative, system_prompt, validate_evidence_claims


def setup_case():
    rules=json.loads((Path(__file__).parents[1]/'config/rules.json').read_text(encoding='utf-8'))
    knowledge=[{'id':f'KB-{i:03d}','category':r['category'],'fault':r['fault'],
                'source':'test.docx','section':r['fault'],'rule_text':r['source_rule_text']} for i,r in enumerate(rules,1)]
    # Three different periods; only the middle period satisfies the bearing ratio.
    values={'velocity_rms':['3','3','6'],'kurtosis':['2','4','2'],
            'low_frequency_impulse':['1','10','1'],'acceleration_peak':['2','10','2'],
            'acceleration_rms':['2','2','2']}
    times=['2026-01-01 10:00:00','2026-01-02 10:00:00','2026-01-03 10:00:00']
    datasets=[]
    for code,ys in values.items():
        datasets.append({'kind':'trend','feature_code':code,'dataset_id':code,'name':code,
                         'data_file':code+'.csv','y_axis':{'unit':'1'},'source_id':code,
                         'rows':[{'x':t,'y':y,'source_row':str(i+2)} for i,(t,y) in enumerate(zip(times,ys))]})
    datasets.append({'kind':'spectrum','dataset_id':'S','acquisition':{'measured_time':None}})
    orders=[{'order':i,'hz':50*i,'amplitude':'2' if i==1 else '.01','file':'spectrum.csv',
             'dataset_id':'S','source_row':str(i+2),'unit':'m/s²'} for i in [1,2,3,4,6,8,9]]
    s={'mode':'real_measurement','case_id':'TEST','device':{'type':rules[0]['category']},'datasets':datasets,
       'waveform':None,'case_manifest':{'latest_acquisition':{'dataset_ids':['S']},'operating_condition':{}},'processing':{}}
    a={'order_coordinates':orders,'warnings':[],'missing':[],'spectrum_provided':True,'series':[],'evidence_items':[]}
    return s,a,rules,knowledge


def test_full_history_and_latest_shared_spectrum_are_used():
    s,a,r,k=setup_case();d=match_rules(s,a,r,k)
    bearing=d['rules'][0]
    assert [x['matched'] for x in bearing['records']]==[0,3,0]
    assert bearing['all_met_count']==1 and bearing['complete_count']==3
    assert bearing['best']['time']=='2026-01-02T10:00:00'
    assert bearing['latest']['matched']==0  # Middle record is not hidden by equal endpoints.
    unbalance=d['rules'][1]
    assert unbalance['records'][0]['matched']==4
    assert unbalance['records'][2]['matched']==2
    for row in unbalance['records']:
        assert row['conditions'][0]['value'] is not None
        assert row['conditions'][0]['sources'][0]['file']=='spectrum.csv'
        assert row['spectrum_reference']=='shared_latest'
    assert unbalance['all_met_count']==1
    assert d['historical_time_count']==3 and '工况' not in d['state']


def test_misaligned_timestamps_are_not_paired():
    s,a,r,k=setup_case()
    next(d for d in s['datasets'] if d.get('feature_code')=='acceleration_rms')['rows'][1]['x']='2026-01-02 10:00:01'
    d=match_rules(s,a,r,k)
    middle=d['rules'][0]['records'][1]
    assert middle['matched']==2 and middle['unknown']==1
    assert middle['conditions'][2]['value'] is None
    assert d['historical_time_count']==4


def test_zero_denominator_is_unknown_not_pass():
    s,a,r,k=setup_case()
    next(d for d in s['datasets'] if d.get('feature_code')=='acceleration_rms')['rows'][1]['y']='0'
    row=match_rules(s,a,r,k)['rules'][0]['records'][1]
    assert row['matched']==2 and row['unknown']==1 and '零' in row['conditions'][2]['reason']


@pytest.mark.parametrize('value,expected',[('2.8','满足'),('4.5','不满足'),('2.7999999999999999','不满足')])
def test_exact_threshold_boundaries(value,expected):
    c={'id':'C','name':'range','metric':'velocity_rms','gte':2.8,'lt':4.5}
    assert run_condition(c,{'velocity_rms':{'value':value}}, {})['status']==expected


def test_unknown_order_is_not_substituted_or_interpolated():
    s,a,r,k=setup_case();a['order_coordinates']=[x for x in a['order_coordinates'] if x['order']!=8]
    rows=match_rules(s,a,r,k)['rules'][1]['records']
    assert all(x['conditions'][1]['status']=='无法判定' for x in rows)
    assert rows[0]['matched']==3 and rows[0]['total']==4
    assert rows[0]['match_rate']==.75


def test_missing_work_state_does_not_block_rules():
    s,a,r,k=setup_case();s['device'].update(load=None,direction=None)
    assert len(match_rules(s,a,r,k)['rules'][0]['records'])==3


def test_motor_component_uses_motor_rules_without_changing_asset_class():
    s,a,r,k=setup_case();s['device'].update(type='机械臂',component='电机驱动端')
    d=match_rules(s,a,r,k)
    assert d['diagnostic_category']=='电动机' and d['rules'][0]['record_count']==3
    assert s['device']['type']=='机械臂'


def test_changed_document_and_wrong_category_do_not_silently_execute():
    s,a,r,k=setup_case();k[0]['rule_text']='changed'
    assert match_rules(s,a,r,k)['rules'][0]['status']=='来源规则已变化，需核对配置'
    s['device']['type']='其他设备'
    assert all(x['status']=='设备类别不适用' for x in match_rules(s,a,r,k)['rules'])


def test_rule_config_can_be_edited_but_not_execute_code():
    s,a,r,k=setup_case();assert validate_rules(r)
    r[0]['conditions'][0]['metric']='__import__("os")'
    with pytest.raises(ValueError):validate_rules(r)


@pytest.mark.parametrize('count,label',[(0,'未获得规则支持'),(1,'支持较弱'),(2,'部分符合'),(3,'疑似，建议优先排查'),(4,'高度疑似（规则全部符合）')])
def test_support_labels_are_not_probabilities(count,label):
    assert support(count,4)==label


def test_csv_contains_all_conditions_and_sources(tmp_path):
    s,a,r,k=setup_case();d=match_rules(s,a,r,k);p=tmp_path/'matches.csv';write_matches_csv(d,p)
    with p.open(encoding='utf-8-sig') as f:rows=list(csv.reader(f))
    assert len(rows)==1+3*(3+4+4+2)
    assert any('acceleration_peak.csv' in str(row) for row in rows)


def test_writer_receives_history_computation_not_only_endpoints():
    s,a,r,k=setup_case();d=match_rules(s,a,r,k);facts=real_facts(s,a,d)
    assert 'records' not in facts['decision']['rules'][0]  # Detailed CSV exists; no silent truncation.
    assert facts['decision']['rules'][0]['condition_summary'][2]['matched']==1
    assert facts['decision']['rules'][0]['historical_best']['matched']==3
    content,budget=prepare_context(facts,k)
    assert 'mechanism_matching_v2' in content and '全部' in system_prompt(facts)
    assert budget['input_token_upper_bound']<65536
    text={'mechanism':'规则程序已对全部记录逐项匹配。','limitations':'历史记录共用最新频谱参考。',
          'action1':'建议根据支持等级核对对应部件。','action2':'建议记录检查及处置后的结果。','citations':[],'hypotheses':[]}
    assert validate_real_narrative(text,[],facts)
    bad=deepcopy(text);bad['limitations']='缺少运行状态及工况，无法进行判断。'
    with pytest.raises(ValueError,match='工况'):validate_real_narrative(bad,[],facts)
    bad=deepcopy(text);bad['hypotheses']=[{'fault':'新故障'}]
    with pytest.raises(ValueError,match='另行诊断'):validate_real_narrative(bad,[],facts)


@pytest.mark.parametrize('sentence',[
    '不能声称目视观察到冲击或周期波形。',
    '不能根据这些记录证明持续上升。',
    '不应声称未提供波形。',
])
def test_negated_observation_is_not_fabrication(sentence):
    text={'mechanism':sentence,'limitations':'历史共用最新频谱参考。','action1':'请对照条件记录核对部件。','action2':'请记录检查处置结果。'}
    assert validate_evidence_claims(text,{'mode':'real_measurement','availability':{'raw_waveform_provided':True}})


def test_negation_in_previous_clause_does_not_allow_fabrication():
    text={'mechanism':'不能判定故障，但波形显示冲击。','limitations':'历史共用最新频谱参考。','action1':'请对照条件记录核对部件。','action2':'请记录检查处置结果。'}
    with pytest.raises(ValueError):validate_evidence_claims(text,{'mode':'real_measurement','availability':{'raw_waveform_provided':True}})
