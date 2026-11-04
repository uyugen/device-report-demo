"""Manage only this project's CPU Qwen service on the server's loopback interface."""
from pathlib import Path
import argparse,json,os,secrets,signal,socket,subprocess,time,urllib.error,urllib.request

PROJECT=Path(__file__).resolve().parents[1]

def settings():
    cfg=json.loads((PROJECT/'config/qwen_local.json').read_text())
    if cfg['host']!='127.0.0.1' or cfg['gpu_layers']!=0:
        raise ValueError('此启动器仅允许本机CPU服务；GPU部署须单独确认设备分配')
    root=Path(cfg['runtime_root']).resolve()
    for key in ['binary','model_file']:
        if not (root/cfg[key]).resolve().is_relative_to(root):raise ValueError('模型或运行时路径越界')
    return cfg,root

def owned_process(root):
    try:
        pid=int((root/'server.pid').read_text());proc=Path(f'/proc/{pid}')
        if proc.stat().st_uid!=os.getuid():return None
        if (proc/'cwd').resolve()!=root:return None
        cmd=(proc/'cmdline').read_bytes()
        return pid if b'llama-server' in cmd and b'Qwen3.5-9B-Q4_K_M' in cmd else None
    except (OSError,ValueError):return None

def health(cfg,root):
    try:
        req=urllib.request.Request(f"http://{cfg['host']}:{cfg['port']}/health")
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=2) as r:
            return json.load(r).get('status')=='ok'
    except (OSError,ValueError):return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status'],default='status',nargs='?')
    args=parser.parse_args();cfg,root=settings();pid=owned_process(root)
    if args.action=='start' and not pid:
        binary=root/cfg['binary'];model=root/cfg['model_file']
        if not binary.is_file() or not model.is_file():raise SystemExit('模型或运行时尚未准备完成')
        if not (root/'model_manifest.json').exists():raise SystemExit('缺少已校验的模型清单')
        with socket.socket() as probe:
            try:probe.bind((cfg['host'],cfg['port']))
            except OSError:raise SystemExit('模型端口已被其他服务占用；未停止它')
        key=root/'api-key'
        if not key.exists():
            fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
        (root/'logs').mkdir(exist_ok=True)
        command=['nice','-n','10',str(binary),'--model',str(model),'--alias',cfg['model_name'],
                 '--host',cfg['host'],'--port',str(cfg['port']),'--ctx-size',str(cfg['context_tokens']),
                 '--threads',str(cfg['threads']),'--threads-batch',str(cfg['threads']),
                 '--n-gpu-layers','0','--parallel','1','--batch-size','512','--ubatch-size','128',
                 '--jinja','--chat-template-kwargs','{"enable_thinking":false}',
                 '--api-key-file',str(key)]
        env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']='';env['OMP_NUM_THREADS']=str(cfg['threads'])
        with (root/'logs/server.log').open('ab') as log:
            p=subprocess.Popen(command,cwd=root,stdout=log,stderr=log,env=env,start_new_session=True)
        (root/'server.pid').write_text(str(p.pid));pid=p.pid
        for _ in range(30):
            if p.poll() is not None:raise SystemExit('模型服务启动失败，查看独立日志logs/server.log')
            if health(cfg,root):break
            time.sleep(1)
    elif args.action=='stop' and pid:
        os.kill(pid,signal.SIGTERM)
        for _ in range(100):
            if owned_process(root)!=pid:break
            time.sleep(.1)
        else:raise SystemExit('模型进程尚未退出，未强制终止')
        (root/'server.pid').unlink(missing_ok=True);pid=None
    print(json.dumps({'running':bool(pid),'ready':bool(pid and health(cfg,root)),
                      'pid':pid,'model':cfg['model_name'],'execution':'CPU','threads':cfg['threads'],
                      'url':f"http://{cfg['host']}:{cfg['port']}/v1"},ensure_ascii=False))

if __name__=='__main__':main()
