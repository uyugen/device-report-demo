import json,sqlite3,time,hashlib
from datetime import datetime,timezone
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from .signal_data import simulate,analyse
from .rules import evaluate
from .knowledge import retrieve
from .charts import draw
from .writer import write_report
from .export import export_docx,export_pdf

ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'workspace';WORK.mkdir(exist_ok=True)
DB=WORK/'runs.sqlite3'
with sqlite3.connect(DB) as c:c.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT, payload TEXT)')
def save(run_id,status,payload):
    with sqlite3.connect(DB) as c:c.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?)',(run_id,status,json.dumps(payload,ensure_ascii=False)))
def load(run_id):
    with sqlite3.connect(DB) as c:row=c.execute('SELECT status,payload FROM runs WHERE id=?',(run_id,)).fetchone()
    return {'status':row[0],**json.loads(row[1])} if row else None
class State(TypedDict,total=False):
    run_id:str;scenario:str;use_llm:bool;events:list;snapshot:dict;analysis:dict;decision:dict
    knowledge:list;text:dict;writer:dict;summary:str;pdf:dict;output:dict;rules:list

def log(state,label):
    state['events']=[*state.get('events',[]),{'step':label,'time':datetime.now(timezone.utc).isoformat()}]
    save(state['run_id'],'running',{'id':state['run_id'],'scenario':state['scenario'],'events':state['events']})
    return state
def collect(s):
    log(s,'读取模拟设备与采集数据');s['snapshot']=simulate(s['scenario']);return s
def quality(s):
    snap=s['snapshot']
    if snap['sample_count']/snap['sampling_rate']!=snap['duration_seconds']:raise ValueError('采样参数不一致')
    log(s,'核对测点、时间、单位与采样参数');return s
def algorithms(s):
    s['analysis']=analyse(s['snapshot']);log(s,'计算时域特征与幅值频谱');return s
def rules(s):
    s['rules']=json.loads((ROOT/'config/rules.json').read_text())
    s['decision']=evaluate(s['snapshot'],s['analysis'],s['rules']);log(s,'执行规则并列出未知条件');return s
def knowledge(s):
    path=WORK/'knowledge.json';records=json.loads(path.read_text()) if path.exists() else []
    s['knowledge']=retrieve(records);log(s,'检索电动机机理与措施');return s
def write(s):
    facts={'mode':'simulated','decision':s['decision'],'missing':s['analysis']['missing'],'rpm_available':s['analysis']['rpm_available']}
    s['text'],s['writer']=write_report(facts,s['knowledge'],s['use_llm']);log(s,'编写机理说明与检维修建议');return s
def render(s):
    out=WORK/s['run_id'];out.mkdir(exist_ok=True)
    draw(s['snapshot'],s['analysis'],out);log(s,'按同一数据快照绘制趋势、波形与频谱');return s
def validate(s):
    # Deterministic report values remain outside model-generated text.
    if s['decision']['fault']!='未定位' or s['decision']['severity']!='未分级':raise ValueError('未经审核的结论')
    if s['analysis']['features']:
        f=s['analysis']['features']
        if abs(f['crest_factor']-f['acceleration_peak']/f['acceleration_rms'])>1e-9:raise ValueError('峰值因子不一致')
        if abs(f['velocity_rms']-s['snapshot']['history'][-1]['velocity_rms'])>1e-9:raise ValueError('趋势与当前波形不一致')
    log(s,'检查数值、引用与结论边界');return s
def export(s):
    out=WORK/s['run_id'];s['summary']=export_docx(ROOT/'inputs/reference.docx',s['snapshot'],s['analysis'],s['decision'],s['text'],out)
    s['pdf']=export_pdf(out);log(s,'生成Word与PDF并归档依据');return s

builder=StateGraph(State)
nodes=[collect,quality,algorithms,rules,knowledge,write,render,validate,export]
last=START
for node in nodes:builder.add_node(node.__name__,node);builder.add_edge(last,node.__name__);last=node.__name__
builder.add_edge(last,END)
GRAPH=builder.compile()

def run(run_id,scenario,use_llm):
    try:
        s=GRAPH.invoke({'run_id':run_id,'scenario':scenario,'use_llm':use_llm,'events':[]})
        out=WORK/run_id
        # Persist complete data locally, but keep arrays out of API status and model prompts.
        (out/'snapshot.json').write_text(json.dumps(s['snapshot'],ensure_ascii=False),encoding='utf-8')
        evidence={'decision':s['decision'],'analysis':{k:v for k,v in s['analysis'].items() if k not in ['frequency','amplitude']},
                  'knowledge':s['knowledge'],'writer':s['writer'],'processing':s['snapshot']['processing'],
                  'rules':s['rules'],'template_sha256':hashlib.sha256((ROOT/'inputs/reference.docx').read_bytes()).hexdigest()}
        (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'id':run_id,'scenario':scenario,'mode':'simulated','events':s['events'],
                'device':s['snapshot']['device'],'measured_time':s['snapshot']['measured_time'],
                'summary':s['summary'],'decision':s['decision'],'analysis':evidence['analysis'],
                'knowledge':s['knowledge'],'writer':s['writer'],'text':s['text'],'pdf':s['pdf'],
                'processing':s['snapshot']['processing']}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        save(run_id,'done',report)
    except Exception as e:
        old=load(run_id) or {};save(run_id,'failed',{'id':run_id,'events':old.get('events',[]),'error':f'{type(e).__name__}: {str(e)[:200]}'})
        raise
