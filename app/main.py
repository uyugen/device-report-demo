from pathlib import Path
import json,os,uuid,threading
from datetime import datetime
from fastapi import FastAPI,HTTPException,UploadFile,File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from .pipeline import ROOT,WORK,run,save,load
from .signal_data import SCENARIOS
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
def config():return {'scenarios':SCENARIOS,'model_enabled':os.getenv('LLM_ENABLED','false').lower()=='true' and bool(os.getenv('MODEL_API_KEY')),'project_root':str(ROOT)}
@app.get('/api/health')
def health():return {'status':'ok','project':'device-report-demo'}
class Request(BaseModel):
    scenario:str='rising'
    use_llm:bool=False
@app.post('/api/reports')
def create(req:Request):
    if req.scenario not in SCENARIOS:raise HTTPException(400,'未知场景')
    if not lock.acquire(blocking=False):raise HTTPException(409,'已有报告正在生成，请稍后重试')
    rid=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    save(rid,'running',{'id':rid,'events':[],'scenario':req.scenario})
    def work():
        try:run(rid,req.scenario,req.use_llm)
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
    allowed=['report.docx','report.pdf','trend.png','waveform.png','spectrum.png','evidence.json','snapshot.json']
    if name not in allowed or not (WORK/rid/name).is_file():raise HTTPException(404,'文件不存在')
    return FileResponse(WORK/rid/name,filename=name)
@app.get('/api/knowledge')
def knowledge():
    p=WORK/'knowledge.json';return json.loads(p.read_text()) if p.exists() else []
@app.post('/api/knowledge')
async def upload(file:UploadFile=File(...)):
    if not file.filename.lower().endswith('.docx'):raise HTTPException(400,'请上传DOCX知识文档')
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise HTTPException(400,'文件不能超过5MB')
    if not lock.acquire(blocking=False):raise HTTPException(409,'报告生成中，暂不能更新知识库')
    try:
        inputs=ROOT/'inputs';inputs.mkdir(exist_ok=True);p=inputs/'uploaded_knowledge.docx';p.write_bytes(raw)
        records=import_knowledge(p,WORK/'knowledge.json');return {'count':len(records)}
    except Exception as e:raise HTTPException(400,'知识文档解析失败：'+type(e).__name__)
    finally:lock.release()
@app.get('/api/rules')
def rules():return json.loads((ROOT/'config/rules.json').read_text())
@app.put('/api/rules')
def update_rules(payload:list):
    try:validate_rules(payload)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(400,str(e))
    if not lock.acquire(blocking=False):raise HTTPException(409,'报告生成中，暂不能更新规则')
    try:
        path=ROOT/'config/rules.json';temp=path.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));temp.replace(path)
    finally:lock.release()
    return {'saved':True}
