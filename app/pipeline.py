import json,sqlite3,time,hashlib
from datetime import datetime,timezone
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from .signal_data import analyse
from .case_data import parse_zip,check_snapshot
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
    run_id:str;case_id:str;case_path:str;use_llm:bool;events:list;snapshot:dict;analysis:dict;decision:dict
    knowledge:list;text:dict;writer:dict;summary:str;pdf:dict;output:dict;rules:list

def log(state,label):
    import inspect
    state['events']=[*state.get('events',[]),{'node':inspect.currentframe().f_back.f_code.co_name,'step':label,'time':datetime.now(timezone.utc).isoformat()}]
    save(state['run_id'],'running',{'id':state['run_id'],'case_id':state['case_id'],'events':state['events']})
    return state
def collect(s):
    s['snapshot']=parse_zip(Path(s['case_path']).read_bytes())
    log(s,'解析上传案例：台账、特征与图谱及来源对应');return s
def quality(s):
    s['snapshot']['quality']=check_snapshot(s['snapshot'])
    log(s,'核对必填字段、单位、时间对应关系与采样参数');return s
def prepare_evidence(s):
    s['analysis']=analyse(s['snapshot']);log(s,'整理客户最终值与来源，读取倍频精确坐标，不复算信号' if s['snapshot'].get('mode')=='real_measurement' else '整理模拟案例特征与复算依据');return s
def rules(s):
    s['rules']=json.loads((ROOT/'config/rules.json').read_text())
    from .rules import validate_rules
    validate_rules(s['rules'])
    path=WORK/'knowledge.json';records=json.loads(path.read_text()) if path.exists() else []
    s['decision']=evaluate(s['snapshot'],s['analysis'],s['rules'],records)
    if s['snapshot'].get('mode')=='real_measurement':
        if s['decision'].get('profile')=='mechanism_matching_v2':
            from .reader_report import build_report_plan
            plan=build_report_plan(s['snapshot'],s['analysis'],s['decision'],s['rules'])
            s['analysis']['report_plan']=plan
            s['analysis']['available_chart_manifest']=s['analysis']['chart_manifest']
            s['analysis']['chart_manifest']=plan['charts']
        from .mechanism_rules import write_matches_csv
        from .real_data import report_limitations
        s['analysis']['missing']=report_limitations(s['analysis']['missing'])
        s['snapshot']['quality']['limitations']=s['analysis']['missing']
        out=WORK/s['run_id'];out.mkdir(exist_ok=True)
        write_matches_csv(s['decision'],out/'rule_matches.csv')
    log(s,'逐时刻执行机理条件、比值与满足数统计；共用最新频谱参考');return s
def knowledge(s):
    path=WORK/'knowledge.json';records=json.loads(path.read_text()) if path.exists() else []
    s['knowledge']=retrieve(records);log(s,f'载入全部知识条目（{len(records)}条，不过滤、不截断）');return s
def write(s):
    snap=s['snapshot'];a=s['analysis']
    if snap.get('mode')=='real_measurement':
        from .real_data import real_facts
        facts=real_facts(snap,a,s['decision'])
    else:
        facts=simulation_facts(snap,a,s['decision'])
    out=WORK/s['run_id'];out.mkdir(exist_ok=True)
    from .writer import system_prompt
    (out/'writer_input.json').write_text(json.dumps({'system_prompt':system_prompt(facts),'facts':facts,'knowledge':s['knowledge']},ensure_ascii=False,indent=2),encoding='utf-8')
    s['text'],s['writer']=write_report(facts,s['knowledge'],s['use_llm'])
    if a.get('report_plan',{}).get('version')=='reader_report_v3':
        from .reader_report import merge_report_citations
        s['text'],s['writer']['citation_sources']=merge_report_citations(s['text'],a['report_plan'],s['knowledge'])
    log(s,'结合实测依据与全部知识编写机理分析及建议');return s

def simulation_facts(snap,a,decision):
    return {'mode':'simulated','case_id':snap['case_id'],'device':snap['device'],
           'availability':{'raw_waveform_provided':snap['waveform'] is not None,
                           'raw_waveform_array_omitted_from_prompt':True,
                           'spectrum_computed':bool(a['frequency']),
                           'note':'原始波形如已提供，由程序复算特征并绘图；仅为控制长度不将数组传给模型，不能据此说缺少波形。'},
           'measurement':{k:snap[k] for k in ['measured_time','sampling_rate','sample_count','duration_seconds','unit','feature_units']},
           'uploaded_current_features':a['uploaded_features'],'recomputed_features':a['recomputed_features'],
           'analysis_features':a['features'],'feature_source':a['feature_source'],'feature_comparisons':a['comparisons'],
           'history_features':snap['history'],'trend_statistics':{k:decision[k] for k in ['first','last','change_percent','trend_count','trend_start','trend_end']},
           'spectrum_peaks':a['peaks'],'spectrum_amplitude_unit':'m/s²（单边峰值幅度）',
           'decision':decision,'missing':a['missing'],'data_warnings':a['warnings'],
           'rpm_available':a['rpm_available'],'processing':snap['processing']}
def render(s):
    out=WORK/s['run_id'];out.mkdir(exist_ok=True)
    draw(s['snapshot'],s['analysis'],out);log(s,'按同一数据快照绘制趋势、波形与频谱');return s
def validate(s):
    # Deterministic report values remain outside model-generated text.
    if s['decision']['severity']!='未分级':raise ValueError('未经审核的严重程度')
    if s['decision'].get('profile')=='mechanism_matching_v2':
        from .mechanism_rules import summarize
        for rule in s['decision']['rules']:
            for row in rule.get('records',[]):
                if any(row[k]!=v for k,v in summarize(row['conditions']).items()):raise ValueError('条件计数与逐次记录不一致')
    elif s['decision']['fault']!='未定位':raise ValueError('未经审核的结论')
    if s['snapshot'].get('mode')=='real_measurement':
        if s['analysis']['signal_recalculation'] or s['analysis']['history_linked_to_latest']:
            raise ValueError('真实数据不得复算信号或未经确认绑定采集')
    if s['analysis']['recomputed_features']:
        f=s['analysis']['features']
        if f['acceleration_rms'] and abs(f['crest_factor']-f['acceleration_peak']/f['acceleration_rms'])>1e-9:raise ValueError('峰值因子不一致')
    log(s,'检查数值、引用与结论边界');return s
def export(s):
    out=WORK/s['run_id'];s['summary']=export_docx(ROOT/'inputs/reference.docx',s['snapshot'],s['analysis'],s['decision'],s['text'],out,s['knowledge'],s['writer'])
    s['pdf']=export_pdf(out);log(s,'生成Word与PDF并归档依据');return s

builder=StateGraph(State)
nodes=[collect,quality,prepare_evidence,rules,knowledge,write,render,validate,export]
last=START
for node in nodes:builder.add_node(node.__name__,node);builder.add_edge(last,node.__name__);last=node.__name__
builder.add_edge(last,END)
GRAPH=builder.compile()

def run(run_id,case_id,case_path,use_llm):
    try:
        s=GRAPH.invoke({'run_id':run_id,'case_id':case_id,'case_path':str(case_path),'use_llm':use_llm,'events':[]})
        out=WORK/run_id
        # Persist complete data locally, but keep arrays out of API status and model prompts.
        (out/'snapshot.json').write_text(json.dumps(s['snapshot'],ensure_ascii=False),encoding='utf-8')
        evidence={'decision':s['decision'],'analysis':{k:v for k,v in s['analysis'].items() if k not in ['frequency','amplitude']},
                  'knowledge':s['knowledge'],'writer':s['writer'],'processing':s['snapshot']['processing'],
                  'quality':s['snapshot']['quality'],'case_id':s['snapshot']['case_id'],
                  'rules':s['rules'],'template_sha256':hashlib.sha256((ROOT/'inputs/reference.docx').read_bytes()).hexdigest()}
        (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'id':run_id,'case_id':s['snapshot']['case_id'],'case_title':s['snapshot']['title'],'mode':s['snapshot'].get('mode','simulated'),'events':s['events'],
                'is_test_data':s['snapshot'].get('is_test_data',False),'data_notice':s['snapshot'].get('data_notice',''),
                'device':s['snapshot']['device'],'measured_time':s['snapshot']['measured_time'],
                'summary':s['summary'],'decision':s['decision'],'analysis':evidence['analysis'],
                'knowledge':s['knowledge'],'writer':s['writer'],'text':s['text'],'pdf':s['pdf'],
                'processing':s['snapshot']['processing'],'quality':s['snapshot']['quality']}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        save(run_id,'done',report)
    except Exception as e:
        old=load(run_id) or {};save(run_id,'failed',{'id':run_id,'events':old.get('events',[]),'error':f'{type(e).__name__}: {str(e)[:200]}'})
        raise
