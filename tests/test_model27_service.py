import importlib.util
from pathlib import Path
import json
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/local_model27_service.py'
spec=importlib.util.spec_from_file_location('model27_service',path)
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)


def test_assigned_gpu_and_bounded_request_configuration():
    cfg,root=service.settings()
    assert cfg['gpu_device']==5 and cfg['port']==8057
    assert cfg['context_tokens']==65536
    cmd=service.command(cfg,root)
    def value(flag):return cmd[cmd.index(flag)+1]
    assert value('--parallel')=='1'
    assert value('--batch-size')=='512' and value('--ubatch-size')=='128'
    assert value('--cache-type-k')==value('--cache-type-v')=='q8_0'
    assert value('--host')=='127.0.0.1'
    assert value('--api-key-file')==str(root/'api-key')
    assert '--tensor-split' not in cmd
    assert cfg['gpu_budget_mib']==24576 and cfg['min_free_mib']==2048


@pytest.mark.parametrize('field,value',[
    ('host','0.0.0.0'),('gpu_device',-1),('gpu_device',True),('binary','../other/llama-server'),
    ('model_file','../other/model.gguf'),('gpu_budget_mib',40000),('min_free_mib',0),
    ('cache_type','unsupported'),
])
def test_unsafe_settings_rejected(tmp_path,monkeypatch,field,value):
    cfg,_=service.settings();cfg[field]=value
    (tmp_path/'config').mkdir();(tmp_path/'config/qwen27_local.json').write_text(json.dumps(cfg))
    monkeypatch.setattr(service,'PROJECT',tmp_path)
    with pytest.raises(ValueError):service.settings()


def test_process_memory_uses_only_matching_gpu_and_pid(monkeypatch):
    class Result:
        stdout='GPU-other, 123, 20000\nGPU-assigned, 456, 17000\nGPU-assigned, 123, 21500\n'
    monkeypatch.setattr(service.subprocess,'run',lambda *a,**k:Result())
    assert service.process_memory('GPU-assigned',123)==21500
    assert service.process_memory('GPU-assigned',999)==0


def test_missing_pid_file_cannot_stop_another_task(tmp_path):
    assert service.owned(tmp_path,'server.pid',b'Qwen3.5-27B') is None
