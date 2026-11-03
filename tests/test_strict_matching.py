from copy import deepcopy
import pytest
from app.mechanism_rules import summarize,combine_outcomes,match_rules
from app.reader_report import build_report_plan
from app.real_data import real_facts
from app.writer import validate_reader_narrative,write_report
from test_mechanism_matching import setup_case


@pytest.mark.parametrize('statuses,expected',[
    (['满足']*4,'故障'),
    (['满足']*3+['不满足'],'正常'),
    (['不满足']*4,'正常'),
    (['满足']*3+['无法判定'],'无法判定'),
    (['满足','不满足','无法判定'],'正常'),
    (['无法判定']*4,'无法判定'),
    ([],'无法判定'),
])
def test_conjunction_with_explicit_false_and_unknown(statuses,expected):
    result=summarize([{'status':x} for x in statuses])
    assert result['support']==expected
    assert result['all_conditions_met']==bool(statuses and all(x=='满足' for x in statuses))


@pytest.mark.parametrize('outcomes,blocked,expected',[
    (['故障','正常'],False,'故障'),
    (['故障','无法判定'],True,'故障'),
    (['正常','正常'],False,'正常'),
    (['正常','无法判定'],False,'无法判定'),
    (['正常'],True,'无法判定'),
    ([],False,'无法判定'),
])
def test_fault_rules_are_or_not_and(outcomes,blocked,expected):
    assert combine_outcomes(outcomes,blocked)==expected


def normal_case():
    s,a,r,k=setup_case()
    values={'velocity_rms':'6','kurtosis':'2','low_frequency_impulse':'1',
            'acceleration_peak':'2','acceleration_rms':'2'}
    for dataset in s['datasets']:
        if dataset['kind']=='trend':
            for row in dataset['rows']:row['y']=values[dataset['feature_code']]
    a['chart_manifest']=[]
    return s,a,r,k


def test_current_normal_and_past_fault_are_kept_separate():
    s,a,r,k=setup_case();a['chart_manifest']=[]
    d=match_rules(s,a,r,k)
    assert d['overall_status']=='正常' and not d['candidates']
    assert d['historical_candidates'] and d['historical_status_counts']=={'故障':2,'正常':1}
    plan=build_report_plan(s,a,d,r)
    assert '正常' in plan['conclusion'] and '历史记录曾判定' in plan['conclusion']
    assert all(x['historical_only'] for x in plan['directions'])


def test_normal_input_does_not_raise_partial_faults(monkeypatch):
    s,a,r,k=normal_case();d=match_rules(s,a,r,k)
    assert d['matching_mode']=='all_conditions_required_v1'
    assert d['overall_status']=='正常' and d['fault']=='无对应故障'
    assert not d['candidates'] and not d['historical_candidates']
    assert d['historical_status_counts']=={'正常':3}
    assert all(x['status']=='正常' for x in d['rules'])
    plan=build_report_plan(s,a,d,r);a['report_plan']=plan
    assert plan['charts']==[] and plan['directions']==[]
    facts=real_facts(s,a,d)
    text,info=write_report(facts,k,False)
    assert info['mode']=='template' and '正常' in text['assessment']
    assert validate_reader_narrative(text,[x['id'] for x in k],facts)
    assert text['chart_explanations']==[]


def test_full_match_is_a_fault_even_when_other_rules_normal():
    s,a,r,k=normal_case()
    for dataset in s['datasets']:
        if dataset.get('feature_code')=='velocity_rms':dataset['rows'][-1]['y']='3'
    d=match_rules(s,a,r,k)
    assert d['overall_status']=='故障'
    assert d['candidates'][0]['fault']=='电机转子不平衡'
    assert d['rules'][0]['status']=='正常' and d['rules'][1]['status']=='故障'
    plan=build_report_plan(s,a,d,r)
    assert '判定故障' in plan['conclusion'] and not plan['directions'][0]['historical_only']


def test_changed_knowledge_cannot_turn_unexecuted_rule_into_normal():
    s,a,r,k=normal_case();k[0]['rule_text']='changed'
    d=match_rules(s,a,r,k)
    assert d['overall_status']=='无法判定'
    a['report_plan']=build_report_plan(s,a,d,r)
    facts=real_facts(s,a,d);text,_=write_report(facts,k,False)
    assert '无法判定' in text['assessment']
    assert validate_reader_narrative(text,[x['id'] for x in k],facts)


def test_fault_writer_cannot_contradict_deterministic_outcome():
    s,a,r,k=normal_case()
    for dataset in s['datasets']:
        if dataset.get('feature_code')=='velocity_rms':dataset['rows'][-1]['y']='3'
    d=match_rules(s,a,r,k)
    a['report_plan']=build_report_plan(s,a,d,r)
    facts=real_facts(s,a,d);text,_=write_report(facts,k,False)
    assert validate_reader_narrative(text,[x['id'] for x in k],facts)
    text['assessment']='本次机理判定当前设备状态正常，建议例行监测。'
    with pytest.raises(ValueError):validate_reader_narrative(text,[x['id'] for x in k],facts)


@pytest.mark.parametrize('field,bad',[
    ('mechanism','当前设备健康状态良好，振动、温度稳定。'),
    ('mechanism','频谱与波形未见异常冲击和调制特征。'),
    ('assessment','仍可能存在电机故障，建议优先排查。'),
    ('action2','建议安排转子动平衡或拆检。'),
])
def test_normal_report_does_not_copy_unverified_example_claims(field,bad):
    s,a,r,k=normal_case();d=match_rules(s,a,r,k)
    a['report_plan']=build_report_plan(s,a,d,r)
    facts=real_facts(s,a,d);text,_=write_report(facts,k,False)
    text[field]=bad
    with pytest.raises(ValueError):validate_reader_narrative(text,[x['id'] for x in k],facts)
