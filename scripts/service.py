"""Start/stop only this project's own loopback service."""
from pathlib import Path
import os,signal,subprocess,sys,json,time,urllib.request
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'workspace';WORK.mkdir(exist_ok=True)
PID=WORK/'server.pid'
def owned_process():
    try:
        pid=int(PID.read_text());cwd=Path(f'/proc/{pid}/cwd').resolve()
        cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
        return pid if cwd==ROOT and b'uvicorn' in cmd and b'app.main:app' in cmd else None
    except (OSError,ValueError):return None
action=sys.argv[1] if len(sys.argv)>1 else 'status'
pid=owned_process()
if action=='start' and not pid:
    with (WORK/'server.log').open('ab') as log:
        p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8046'],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
    PID.write_text(str(p.pid));pid=p.pid
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8046/api/health',timeout=1) as r:
                if p.poll() is not None:raise SystemExit('服务进程已退出，请检查workspace/server.log')
                print(r.read().decode());break
        except Exception:time.sleep(.3)
    else:raise SystemExit('启动未成功，请检查workspace/server.log')
elif action=='stop' and pid:
    os.kill(pid,signal.SIGTERM)
    for _ in range(100):
        if owned_process()!=pid:break
        time.sleep(.1)
    else:raise SystemExit('停止尚未完成，请稍后检查状态')
    PID.unlink(missing_ok=True);pid=None
print(json.dumps({'running':bool(pid),'pid':pid,'url':'http://127.0.0.1:8046'}))
