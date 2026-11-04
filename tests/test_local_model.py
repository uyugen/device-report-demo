from copy import deepcopy
import json
import pytest
from app.writer import write_report
from app.main import config
from test_reader_report import sample


@pytest.mark.parametrize('style,base,local',[
    ('llama_cpp','http://127.0.0.1:8056',True),
    ('qwen','http://localhost:8056/v1',True),
    ('openai','https://api.deepseek.com',False),
])
def test_local_and_remote_request_configuration(monkeypatch,style,base,local):
    *_,facts,text=sample()
    calls=[];clients=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(text,ensure_ascii=False)}}]}
    class Client:
        def __init__(self,**kwargs):clients.append(kwargs)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,headers,json):calls.append((url,deepcopy(json)));return Response()
    monkeypatch.setenv('LLM_ENABLED','true');monkeypatch.setenv('MODEL_API_KEY','test-only')
    monkeypatch.setenv('MODEL_API_STYLE',style);monkeypatch.setenv('MODEL_BASE_URL',base)
    monkeypatch.setenv('MODEL_NAME','Qwen3.5-9B-Q4_K_M' if local else 'deepseek-flash')
    monkeypatch.setenv('MODEL_TIMEOUT_SECONDS','900' if local else '100')
    monkeypatch.setattr('app.writer.httpx.Client',Client)
    from test_mechanism_matching import setup_case
    knowledge=setup_case()[3]
    result,info=write_report(facts,knowledge,True)
    assert info['mode']=='llm' and result==text
    url,payload=calls[0]
    assert url.count('/v1')==1 and url.endswith('/chat/completions')
    if style=='llama_cpp':
        fmt=payload['response_format'];assert fmt['type']=='json_schema'
        schema=fmt['json_schema']['schema']
        assert not schema['additionalProperties']
        import re
        pattern=schema['properties']['mechanism']['pattern']
        assert re.fullmatch(pattern,'当前设备状态正常。')
        for invalid in ['历史104次', '中'*161, '正常"状态说明', '正常\\状态说明', '正常\n状态说明']:
            assert not re.fullmatch(pattern,invalid)
        assert schema['properties']['chart_explanations']['minItems']==len(facts['report_spec']['charts'])
        assert schema['properties']['hypotheses']['maxItems']==0
    else:assert payload['response_format']=={'type':'json_object'}
    assert info['deployment']==('local' if local else 'remote')
    assert clients[0]['trust_env']==(not local)
    assert clients[0]['timeout']==(900 if local else 100)
    if local:
        assert payload['chat_template_kwargs']=={'enable_thinking':False}
        assert 'thinking' not in payload
    else:
        assert payload['thinking']=={'type':'disabled'}
        assert 'chat_template_kwargs' not in payload
    assert config()['model_local']==local


def test_invalid_model_timeout_does_not_call_provider(monkeypatch):
    *_,facts,text=sample()
    monkeypatch.setenv('LLM_ENABLED','true');monkeypatch.setenv('MODEL_API_KEY','test-only')
    monkeypatch.setenv('MODEL_BASE_URL','http://127.0.0.1:8056')
    monkeypatch.setenv('MODEL_TIMEOUT_SECONDS','0')
    def forbidden(*args,**kwargs):raise AssertionError('Must not contact provider')
    monkeypatch.setattr('app.writer.httpx.Client',forbidden)
    result,info=write_report(facts,[],True)
    assert info['mode']=='template' and '超时' in info['message']


def test_local_writing_reminders_are_included_in_context_guard(monkeypatch):
    from app.writer import prepare_context
    from test_mechanism_matching import setup_case
    *_,facts,text=sample();knowledge=setup_case()[3]
    monkeypatch.setenv('MODEL_CONTEXT_TOKENS','65536')
    _,budget=prepare_context(facts,knowledge)
    monkeypatch.setenv('MODEL_CONTEXT_TOKENS',str(budget['input_token_upper_bound']+budget['output_reserved_tokens']))
    monkeypatch.setenv('LLM_ENABLED','true');monkeypatch.setenv('MODEL_API_KEY','test-only')
    monkeypatch.setenv('MODEL_API_STYLE','llama_cpp');monkeypatch.setenv('MODEL_BASE_URL','http://127.0.0.1:8056/v1')
    monkeypatch.setenv('MODEL_TIMEOUT_SECONDS','900')
    def forbidden(*args,**kwargs):raise AssertionError('Over-budget request must not contact model')
    monkeypatch.setattr('app.writer.httpx.Client',forbidden)
    _,info=write_report(facts,knowledge,True)
    assert info['mode']=='template' and '包含写作提醒' in info['message']
