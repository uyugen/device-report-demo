from copy import deepcopy
import pytest
from app.reader_report import build_report_plan, fallback_chart_explanations, merge_report_citations
from app.writer import validate_reader_narrative, system_prompt, prepare_context
from test_mechanism_matching import setup_case
from app.mechanism_rules import match_rules
from app.real_data import real_facts


def sample():
    s,a,r,k=setup_case()
    a['chart_manifest']=[{'dataset_id':d['dataset_id'],'kind':d['kind'],'title':d.get('name','频谱'),
                          'file':f'{i}.png','chart_type':'scatter'} for i,d in enumerate(s['datasets'])]
    d=match_rules(s,a,r,k)
    plan=build_report_plan(s,a,d,r);a['report_plan']=plan
    facts=real_facts(s,a,d)
    refs=[x['id'] for x in k]
    text={'mechanism':'最近记录未完整触发故障机理，历史故障结果单独说明。','assessment':'本次机理规则判定为正常；历史记录曾触发故障机理，应分别记录并关注复发情况。',
          'limitations':'历史判断共用最新频谱作为参考。','action1':'建议检查对应部件并记录现场情况。',
          'action2':'建议保留处置记录并安排复测。','citations':refs,'hypotheses':[],
          'chart_explanations':fallback_chart_explanations(plan)}
    return s,a,r,k,d,plan,facts,text


def test_relevant_charts_include_unsatisfied_conditions_and_history():
    s,a,r,k,d,plan,facts,text=sample()
    # Bearing only matched in a middle period: still relevant, never asserted as current.
    bearing=next(x for x in plan['directions'] if x['rule_id']==r[0]['id'])
    assert bearing['historical_only'] and '历史记录曾判定' in plan['conclusion']
    assert any(x['dataset_id']=='acceleration_peak' for x in plan['charts'])
    assert all(x['chart_type']=='line' and x['related_rules'] for x in plan['charts'])
    assert '2/4' not in plan['conclusion'] and '大概率' not in plan['conclusion']
    assert validate_reader_narrative(text,[x['id'] for x in k],facts)


def test_weak_rules_do_not_fill_report_with_unrelated_charts():
    s,a,r,k,d,plan,facts,text=sample()
    for rule in d['rules']:
        for key in ['latest_assessment','best']:
            rule[key].update(match_rate=.75,all_conditions_met=False)
    d['overall_status']='正常'
    plan=build_report_plan(s,a,d,r)
    assert plan['charts']==[] and plan['directions']==[]
    assert '正常' in plan['conclusion']


def test_normal_rule_sources_do_not_depend_on_model_citations():
    s,a,r,k,d,plan,facts,text=sample()
    for rule in d['rules']:
        for key in ['latest_assessment','best']:rule[key]['all_conditions_met']=False
    d['overall_status']='正常'
    plan=build_report_plan(s,a,d,r)
    text['citations']=[]
    merged,sources=merge_report_citations(text,plan,k)
    assert not plan['directions'] and not plan['charts']
    assert merged['citations']==[x['id'] for x in k]
    assert sources['narrative']==[] and sources['rules']==merged['citations']
    assert text['citations']==[]


def test_blocked_rules_are_not_cited_as_executed_and_extra_citations_are_kept():
    s,a,r,k,d,plan,facts,text=sample()
    d['rules'][0].pop('records');d['rules'][0]['status']='禁用'
    d['rules'][0].pop('latest_assessment');d['rules'][0].pop('best')
    plan=build_report_plan(s,a,d,r)
    text['citations']=['OTHER']
    merged,sources=merge_report_citations(text,plan,[*k,{'id':'OTHER'}])
    assert k[0]['id'] not in sources['rules']
    assert merged['citations']==[x['id'] for x in k[1:]]+['OTHER']
    with pytest.raises(ValueError,match='来源不存在'):merge_report_citations(text,plan,[])


def test_prompt_includes_all_knowledge_without_endpoint_evidence():
    s,a,r,k,d,plan,facts,text=sample()
    a['series']=[{'name':'速度','first':{'y':'123456'},'last':{'y':'654321'},'count':3}]
    facts=real_facts(s,a,d)
    assert 'first' not in facts['historical_features'][0]
    assert '机理含义' in system_prompt(facts)
    content,budget=prepare_context(facts,k)
    assert all(x['id'] in content for x in k)
    assert budget['knowledge_count']==len(k)


@pytest.mark.parametrize('mutation',[
    lambda t:t['chart_explanations'].pop(),
    lambda t:t['chart_explanations'][0].update(dataset_id='unknown'),
    lambda t:t['chart_explanations'][0].update(knowledge_ids=['KB-999']),
    lambda t:t['chart_explanations'][0].update(text='本次指标为九百，波形显示冲击。'),
    lambda t:t.update(assessment='程序统计满足三项，部分符合。'),
    lambda t:t.update(mechanism='目前大概率发生电机转子不平衡。'),
    lambda t:t.update(limitations='波形及频谱坐标由程序生成，未提供绝对采集时间。'),
    lambda t:t.update(mechanism='最近记录中峭度值为一点五，未满足相应条件。'),
    lambda t:next(x for x in t['chart_explanations'] if x['dataset_id']=='acceleration_peak').update(text='本次该项符合相应条件，但仍需结合倍频关系及速度水平判断。'),
    lambda t:t['chart_explanations'][0].update(text='模型判断数值是123，建议关注。'),
])
def test_invalid_explanations_and_reader_unfriendly_prose_rejected(mutation):
    s,a,r,k,d,plan,facts,text=sample();bad=deepcopy(text);mutation(bad)
    with pytest.raises(ValueError):validate_reader_narrative(bad,[x['id'] for x in k],facts)


def test_cannot_silently_drop_knowledge_over_budget(monkeypatch):
    s,a,r,k,d,plan,facts,text=sample();monkeypatch.setenv('MODEL_CONTEXT_TOKENS','500')
    with pytest.raises(ValueError,match='未截断'):prepare_context(facts,k)


def test_variable_spectrum_ratios_need_explicit_time_scope():
    s,a,r,k,d,plan,facts,text=sample()
    chart=next(x for x in text['chart_explanations'] if x['dataset_id']=='S')
    chart['text']='倍频幅值未达相应条件，建议结合其余指标综合判断。'
    with pytest.raises(ValueError,match='历史范围'):validate_reader_narrative(text,[x['id'] for x in k],facts)


def test_invalid_model_prose_is_revised_once_without_resending_rejected_text(monkeypatch):
    import json
    from app.writer import write_report
    s,a,r,k,d,plan,facts,text=sample()
    bad=deepcopy(text);bad['mechanism']='本次只有部分符合，尚需现场复核。'
    answers=[bad,text];calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answers[len(calls)-1],ensure_ascii=False)}}]}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,headers,json):calls.append(deepcopy(json));return Response()
    monkeypatch.setenv('LLM_ENABLED','true');monkeypatch.setenv('MODEL_API_KEY','test-only')
    monkeypatch.setenv('MODEL_BASE_URL','https://example.invalid');monkeypatch.setattr('app.writer.httpx.Client',Client)
    result,info=write_report(facts,k,True)
    assert info['mode']=='llm' and result==text and len(calls)==2
    assert len(calls[1]['messages'])==3 and calls[1]['messages'][-1]['role']=='user'
    assert '部分符合' in info['revision_reasons'][0]
    assert not any(m['role']=='assistant' for m in calls[1]['messages'])
