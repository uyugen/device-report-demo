from pathlib import Path
from urllib.parse import urlsplit
import json,os,uuid,threading,re,io
from zipfile import ZipFile,BadZipFile
from datetime import datetime
from fastapi import FastAPI,HTTPException,UploadFile,File,Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from .pipeline import ROOT,WORK,run,save,load
from .signal_data import analyse
from .case_data import parse_zip,check_snapshot,MAX_ZIP
from .knowledge import import_knowledge
from .rules import validate_rules

load_dotenv(ROOT/'.env')
app=FastAPI(title='设备状态报告 Demo')
app.mount('/static',StaticFiles(directory=ROOT/'app/static'),name='static')
lock=threading.Lock()
@app.on_event('startup')
def initial_knowledge():
    source=ROOT/'inputs/knowledge.docx'
    if source.exists() and not (WORK/'knowledge.json').exists():import_knowledge(source,WORK/'knowledge.json')
    # Interrupted runs are not silently left running after a server restart.
    import sqlite3
    from .pipeline import DB
    with sqlite3.connect(DB) as c:
        rows=c.execute("SELECT id,payload FROM runs WHERE status='running'").fetchall()
        for rid,payload in rows:
            p=json.loads(payload);p['error']='服务重启中断了本次任务，请重新生成'
            c.execute('UPDATE runs SET status=?,payload=? WHERE id=?',('failed',json.dumps(p,ensure_ascii=False),rid))

@app.get('/')
def index():return FileResponse(ROOT/'app/static/index.html')
@app.get('/api/config')
def config():return {'samples':[], 'input_profile':'real_measurement_v1.1',
    'model_enabled':os.getenv('LLM_ENABLED','false').lower()=='true' and bool(os.getenv('MODEL_API_KEY')),
    'model_name':os.getenv('MODEL_NAME','未配置'), 'model_host':urlsplit(os.getenv('MODEL_BASE_URL','')).hostname,
    'context_limit':int(os.getenv('MODEL_CONTEXT_TOKENS','65536'))}
@app.get('/api/health')
def health():return {'status':'ok','project':'device-report-demo'}
class Request(BaseModel):
    case_id:str
    use_llm:bool=False

@app.post('/api/cases')
async def upload_case(file:UploadFile=File(...)):
    if not file.filename or not file.filename.lower().endswith('.zip'):raise HTTPException(400,'请上传ZIP案例数据包')
    raw=await file.read(MAX_ZIP+1)
    try:
        snap=parse_zip(raw)
        if snap.get('mode')!='real_measurement':raise ValueError('新版工作台仅接受真实案例输入包，请使用1.1版格式')
        snap['quality']=check_snapshot(snap);a=analyse(snap)
    except (ValueError,TypeError,KeyError,OverflowError) as e:raise HTTPException(400,str(e))
    cid=uuid.uuid4().hex
    folder=WORK/'cases';folder.mkdir(exist_ok=True)
    (folder/f'{cid}.zip').write_bytes(raw)
    preview={'case_id':cid,'title':snap['title'],'device':snap['device'],'mode':snap.get('mode','simulated'),
             'measurement':{k:snap[k] for k in ['measured_time','sampling_rate','sample_count','duration_seconds']},
             'history_count':sum(len(d['rows']) for d in snap.get('datasets',[]) if d['kind']=='trend') if snap.get('mode')=='real_measurement' else len(snap['history']),'has_waveform':snap['waveform'] is not None,
             'warnings':a['warnings'],'limitations':a['missing'],'comparisons':a['comparisons'],
             'features':a['features'],'feature_source':a['feature_source'],
             'series':a.get('series',[]),'chart_manifest':a.get('chart_manifest',[]),
             'order_coordinates':a.get('order_coordinates',[]),'has_spectrum':a.get('spectrum_provided',False)}
    (folder/f'{cid}.json').write_text(json.dumps(preview,ensure_ascii=False))
    return preview

@app.post('/api/reports')
def create(req:Request):
    if not re.fullmatch('[0-9a-f]{32}',req.case_id):raise HTTPException(400,'请先上传案例')
    path=WORK/'cases'/f'{req.case_id}.zip'
    if not path.is_file():raise HTTPException(404,'案例不存在，请重新上传')
    if not lock.acquire(blocking=False):raise HTTPException(409,'已有报告正在生成，请稍后重试')
    rid=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    save(rid,'running',{'id':rid,'events':[],'case_id':req.case_id})
    def work():
        try:run(rid,req.case_id,path,req.use_llm)
        except Exception:pass
        finally:lock.release()
    threading.Thread(target=work,daemon=True).start()
    return {'id':rid}
def get_run(rid):
    if not __import__('re').fullmatch(r'\d{8}_\d{6}_[0-9a-f]{8}',rid):raise HTTPException(404,'报告不存在')
    item=load(rid)
    if not item:raise HTTPException(404,'报告不存在')
    return item
@app.get('/api/reports/{rid}')
def report(rid:str):return get_run(rid)
@app.get('/api/reports/{rid}/files/{name}')
def artifact(rid:str,name:str):
    item=get_run(rid)
    if item['status']!='done':raise HTTPException(409,'报告尚未生成完成')
    allowed=['report.docx','report.pdf','trend.png','waveform.png','spectrum.png','evidence.json','snapshot.json','writer_input.json']
    if item.get('mode')=='real_measurement':allowed += [ch['file'] for ch in item['analysis'].get('chart_manifest',[])]
    if name not in allowed or not (WORK/rid/name).is_file():raise HTTPException(404,'文件不存在')
    return FileResponse(WORK/rid/name,filename=name)
@app.get('/api/knowledge')
def knowledge():
    p=WORK/'knowledge.json';return json.loads(p.read_text()) if p.exists() else []
@app.post('/api/knowledge')
async def upload(file:UploadFile=File(...)):
    if not file.filename or not file.filename.lower().endswith('.docx'):raise HTTPException(400,'请上传DOCX知识文档')
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise HTTPException(400,'文件不能超过5MB')
    if not lock.acquire(blocking=False):raise HTTPException(409,'报告生成中，暂不能更新知识库')
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist())>40*1024*1024:raise ValueError('DOCX展开大小超过40MB')
        inputs=ROOT/'inputs';inputs.mkdir(exist_ok=True);p=inputs/'pending_knowledge.docx';p.write_bytes(raw)
        original=Path(file.filename.replace('\\','/')).name[:200]
        records=import_knowledge(p,WORK/'knowledge.json',source_name=original)
        p.replace(inputs/'uploaded_knowledge.docx')
        return {'count':len(records),'source':original,'message':'已导入全部条目；文中规则仅作为资料，不自动执行'}
    except (ValueError,BadZipFile,KeyError) as e:raise HTTPException(400,'知识文档解析失败：'+str(e))
    except Exception as e:raise HTTPException(400,'知识文档无法读取，请检查DOCX格式和标题结构：'+type(e).__name__)
    finally:lock.release()
@app.get('/api/rules')
def rules():return json.loads((ROOT/'config/rules.json').read_text())
@app.put('/api/rules')
def update_rules(payload:list[dict]=Body(...)):
    try:validate_rules(payload)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(400,str(e))
    if not lock.acquire(blocking=False):raise HTTPException(409,'报告生成中，暂不能更新规则')
    try:
        path=ROOT/'config/rules.json';temp=path.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));temp.replace(path)
    finally:lock.release()
    return {'saved':True}
