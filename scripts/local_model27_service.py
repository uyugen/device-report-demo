"""Manage this user's 27B service on the explicitly assigned shared GPU.

Memory checks are a polling guard, not a driver-level allocation reservation.
No other user's process, GPU power setting, or MPS configuration is changed.
"""
from pathlib import Path
import argparse,json,os,secrets,signal,socket,subprocess,sys,time,urllib.request

PROJECT=Path(__file__).resolve().parents[1]


def settings():
    cfg=json.loads((PROJECT/'config/qwen27_local.json').read_text())
    if cfg['host']!='127.0.0.1':raise ValueError('模型服务仅绑定本机')
    if type(cfg['gpu_device']) is not int or cfg['gpu_device']<0:raise ValueError('须明确分配GPU编号')
    if not 0<cfg['min_free_mib']<cfg['gpu_budget_mib']<cfg['start_free_mib']:
        raise ValueError('GPU显存保护配置无效')
    if cfg['cache_type'] not in {'q8_0','f16'}:raise ValueError('不支持的缓存类型')
    root=Path(cfg['runtime_root']).resolve()
    for key in ['binary','library_dir','model_file']:
        if not (root/cfg[key]).resolve().is_relative_to(root):raise ValueError('路径越界')
    return cfg,root


def owned(root, filename, marker):
    try:
        pid=int((root/filename).read_text());proc=Path(f'/proc/{pid}')
        if proc.stat().st_uid!=os.getuid() or (proc/'cwd').resolve()!=root:return None
        return pid if marker in (proc/'cmdline').read_bytes() else None
    except (OSError,ValueError):return None


def gpu_stats(cfg):
    result=subprocess.run(['nvidia-smi','-i',str(cfg['gpu_device']),
        '--query-gpu=uuid,memory.free','--format=csv,noheader,nounits'],
        check=True,capture_output=True,text=True,timeout=8)
    uuid,free=result.stdout.strip().split(',')
    return uuid.strip(),int(free.strip())


def process_memory(uuid,pid):
    result=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory',
        '--format=csv,noheader,nounits'],check=True,capture_output=True,text=True,timeout=8)
    for row in result.stdout.splitlines():
        parts=[s.strip() for s in row.split(',')]
        if len(parts)==3 and parts[0]==uuid and parts[1]==str(pid):return int(parts[2])
    return 0


def health(cfg):
    try:
        url=f"http://{cfg['host']}:{cfg['port']}/health"
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=2) as r:
            return json.load(r).get('status')=='ok'
    except (OSError,ValueError):return False


def command(cfg,root):
    return ['nice','-n','10',str(root/cfg['binary']),'--model',str(root/cfg['model_file']),
        '--alias',cfg['model_name'],'--host',cfg['host'],'--port',str(cfg['port']),
        '--ctx-size',str(cfg['context_tokens']),'--threads',str(cfg['threads']),
        '--threads-batch',str(cfg['threads']),'--n-gpu-layers',str(cfg['gpu_layers']),
        '--parallel','1','--batch-size',str(cfg['batch_size']),'--ubatch-size',str(cfg['ubatch_size']),
        '--cache-type-k',cfg['cache_type'],'--cache-type-v',cfg['cache_type'],
        '--flash-attn','on','--jinja','--chat-template-kwargs','{"enable_thinking":false}',
        '--api-key-file',str(root/'api-key')]


def guard(cfg,root):
    uuid,free=gpu_stats(cfg)
    if free<cfg['start_free_mib']:raise SystemExit('可用显存不足，未启动27B服务')
    env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=str(cfg['gpu_device'])
    env['OMP_NUM_THREADS']=str(cfg['threads'])
    env['LD_LIBRARY_PATH']=str(root/cfg['library_dir'])+':'+env.get('LD_LIBRARY_PATH','')
    child=subprocess.Popen(command(cfg,root),cwd=root,env=env)
    (root/'server.pid').write_text(str(child.pid))
    def stop(*_):
        if child.poll() is None:child.terminate()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    failures=0;peak=0
    try:
        while child.poll() is None:
            time.sleep(3)
            try:
                current_uuid,free=gpu_stats(cfg);used=process_memory(uuid,child.pid)
                peak=max(peak,used);failures=0
                (root/'resource_status.json').write_text(json.dumps({'gpu_device':cfg['gpu_device'],
                    'pid':child.pid,'used_mib':used,'peak_mib':peak,'free_mib':free,
                    'budget_mib':cfg['gpu_budget_mib'],'updated_epoch':time.time()}))
                if current_uuid!=uuid or used>cfg['gpu_budget_mib'] or free<cfg['min_free_mib']:
                    print('本服务显存保护触发，仅停止本用户27B进程',flush=True);stop();break
            except (OSError,ValueError,subprocess.SubprocessError):
                failures+=1
                if failures>=3:
                    print('无法持续核查GPU资源，仅停止本服务',flush=True);stop();break
        try:child.wait(timeout=30)
        except subprocess.TimeoutExpired:child.kill();child.wait()
    finally:
        stop()
        for name in ['server.pid','guard.pid']:(root/name).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status','guard'])
    args=parser.parse_args();cfg,root=settings()
    if args.action=='guard':guard(cfg,root);return
    pid=owned(root,'server.pid',cfg['model_name'].encode())
    guard_pid=owned(root,'guard.pid',b'local_model27_service.py')
    if args.action=='start' and not (pid or guard_pid):
        for key in ['binary','model_file']:
            if not (root/cfg[key]).is_file():raise SystemExit('模型或运行时尚未准备完成')
        if not (root/'model_manifest.json').is_file():raise SystemExit('缺少模型校验清单')
        _,free=gpu_stats(cfg)
        if free<cfg['start_free_mib']:raise SystemExit('可用显存不足；未停止其他进程')
        with socket.socket() as probe:
            try:probe.bind((cfg['host'],cfg['port']))
            except OSError:raise SystemExit('端口被占用；未停止其他服务')
        root.mkdir(exist_ok=True);(root/'logs').mkdir(exist_ok=True)
        key=root/'api-key'
        if not key.exists():
            fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
        with (root/'logs/server.log').open('ab') as log:
            p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'guard'],cwd=root,
                stdout=log,stderr=log,start_new_session=True)
        (root/'guard.pid').write_text(str(p.pid));guard_pid=p.pid
        for _ in range(20):
            if p.poll() is not None:raise SystemExit('服务启动失败，请查看本任务server.log')
            if health(cfg):break
            time.sleep(1)
        pid=owned(root,'server.pid',cfg['model_name'].encode())
    elif args.action=='stop':
        if guard_pid:os.kill(guard_pid,signal.SIGTERM)
        elif pid:os.kill(pid,signal.SIGTERM)
        for _ in range(100):
            if not owned(root,'server.pid',cfg['model_name'].encode()):break
            time.sleep(.1)
        pid=owned(root,'server.pid',cfg['model_name'].encode())
    print(json.dumps({'running':bool(pid),'ready':bool(pid and health(cfg)),'pid':pid,
        'guard_pid':guard_pid,'model':cfg['model_name'],'gpu_device':cfg['gpu_device'],
        'context_tokens':cfg['context_tokens'],'gpu_budget_mib':cfg['gpu_budget_mib'],
        'url':f"http://{cfg['host']}:{cfg['port']}/v1"},ensure_ascii=False))


if __name__=='__main__':main()
