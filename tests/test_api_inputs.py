import io
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import pytest
from docx import Document
from fastapi.testclient import TestClient
from app import main
from scripts.generate_samples import build


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'ROOT',tmp_path)
    monkeypatch.setattr(main,'WORK',tmp_path/'workspace')
    (tmp_path/'workspace').mkdir();(tmp_path/'config').mkdir()
    rules=[{'id':'D','kind':'demo_trend','name':'演示','source':'非行业标准','enabled':True,'threshold_percent':30}]
    (tmp_path/'config/rules.json').write_text(json.dumps(rules))
    build(tmp_path/'samples')
    # No lifespan here: input endpoints are isolated from the production runs DB.
    return TestClient(main.app)


def test_zip_http_and_missing_evidence(client):
    raw=(main.ROOT/'samples/missing.zip').read_bytes()
    r=client.post('/api/cases',files={'file':('missing.zip',raw,'application/zip')})
    assert r.status_code==200
    d=r.json();assert not d['has_waveform'] and d['features']['velocity_rms'] is not None
    assert len(d['case_id'])==32 and d['limitations']


def test_invalid_zip_http(client):
    assert client.post('/api/cases',files={'file':('bad.zip',b'not a zip')}).status_code==400
    assert client.post('/api/reports',json={'scenario':'rising'}).status_code==422
    assert client.post('/api/reports',json={'case_id':'../escape'}).status_code==400


def test_rules_accept_json_and_are_independent_of_docx(client):
    rules=client.get('/api/rules').json()
    assert client.put('/api/rules',json=rules).status_code==200
    d=Document();d.add_heading('风机',1);d.add_heading('不平衡',2)
    d.add_paragraph('机理现象：典型现象');d.add_paragraph('机理规则：自动启用全部规则')
    stream=io.BytesIO();d.save(stream)
    r=client.post('/api/knowledge',files={'file':('原始知识.docx',stream.getvalue())})
    assert r.status_code==200 and r.json()['count']==1
    record=client.get('/api/knowledge').json()[0]
    assert record['source']=='原始知识.docx' and record['rule_text']=='自动启用全部规则'
    assert client.get('/api/rules').json()==rules


def test_failed_knowledge_import_keeps_old_entries(client):
    path=main.WORK/'knowledge.json';path.write_text('[{"id":"KEEP"}]')
    r=client.post('/api/knowledge',files={'file':('bad.docx',b'bad')})
    assert r.status_code==400 and json.loads(path.read_text())==[{'id':'KEEP'}]
