"""Upload supplied examples to a dedicated instance and verify report exports."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import sys
import time
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(args):
    base = args.base_url.rstrip('/')
    manifest = json.loads((ROOT/'examples/manifest.json').read_text(encoding='utf-8'))
    for entry in [manifest['knowledge'], *manifest['cases']]:
        assert hashlib.sha256((ROOT/'examples'/entry['file']).read_bytes()).hexdigest() == entry['sha256'], 'Example hash mismatch'
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=base, timeout=60, trust_env=False) as client:
        def get(path):
            response = client.get(path)
            response.raise_for_status()
            return response.json()

        assert get('/api/health')['status'] == 'ok'
        config = get('/api/config')
        if args.use_llm and not config['model_enabled']:
            raise RuntimeError('Model not enabled; configure .env and restart the dedicated instance')
        existing = get('/api/knowledge')
        if existing:
            # Do not replace a company's knowledge library if given a wrong URL.
            from app.knowledge import import_knowledge
            import tempfile
            with tempfile.TemporaryDirectory() as folder:
                sample = import_knowledge(ROOT/'examples'/manifest['knowledge']['file'], Path(folder)/'k.json')
            keys = ['category', 'fault', 'rule_text', 'phenomena', 'causes', 'actions']
            if [{k: r[k] for k in keys} for r in existing] != [{k: r[k] for k in keys} for r in sample]:
                raise RuntimeError('This instance contains another knowledge library; refusing to replace it. Use a fresh checkout and a separate port.')
        else:
            path = ROOT/'examples'/manifest['knowledge']['file']
            with path.open('rb') as stream:
                response = client.post('/api/knowledge', files={'file': (path.name, stream, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
            response.raise_for_status()
            assert response.json()['count'] == manifest['knowledge']['count']
        results = []
        for case in manifest['cases']:
            path = ROOT/'examples'/case['file']
            with path.open('rb') as stream:
                response = client.post('/api/cases', files={'file': (path.name, stream, 'application/zip')})
            response.raise_for_status()
            response = client.post('/api/reports', json={'case_id': response.json()['case_id'], 'use_llm': args.use_llm})
            response.raise_for_status()
            rid = response.json()['id']
            deadline = time.monotonic() + args.timeout
            while True:
                report = get('/api/reports/' + rid)
                if report['status'] == 'done':
                    break
                if report['status'] == 'failed':
                    raise RuntimeError(str(report.get('error')))
                if time.monotonic() > deadline:
                    raise TimeoutError('Report still running: ' + rid + '; inspect the instance before retrying')
                time.sleep(1)
            decision = report['decision']
            assert decision['overall_status'] == case['expected_status'], decision['state']
            assert sorted(c['fault'] for c in decision['candidates']) == sorted(case['expected_faults'])
            assert decision['historical_status_counts'].get('故障', 0) == case['history_fault']
            assert decision['historical_status_counts'].get('正常', 0) == case['history_normal']
            assert all(r.get('record_count') == 24 and r.get('complete_count') == 24 and r.get('knowledge_id') for r in decision['rules'])
            assert report['analysis']['chart_manifest'][-1]['kind'] == 'health_score'
            assert [e['node'] for e in report['events']] == ['collect', 'quality', 'prepare_evidence', 'rules', 'knowledge', 'write', 'render', 'validate', 'export']
            if args.use_llm:
                assert report['writer']['mode'] == 'llm', report['writer'].get('message')
            else:
                assert report['writer']['mode'] == 'template'
            folder = output/path.stem/rid
            folder.mkdir(parents=True, exist_ok=True)
            (folder/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            names = ['report.docx', 'evidence.json', 'rule_matches.csv']
            if report.get('pdf', {}).get('available'):
                names.append('report.pdf')
            elif args.require_pdf:
                raise RuntimeError('PDF missing: ' + str(report.get('pdf')))
            for name in names:
                response = client.get(f'/api/reports/{rid}/files/{name}')
                response.raise_for_status()
                raw = response.content
                if name.endswith('.docx'):
                    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                        assert archive.testzip() is None and 'word/document.xml' in archive.namelist()
                if name.endswith('.pdf'):
                    assert raw.startswith(b'%PDF-')
                (folder/name).write_bytes(raw)
            result = {'case': path.name, 'report_id': rid, 'status': decision['overall_status'],
                      'history': decision['historical_status_counts'],
                      'writer': report['writer']['mode'], 'pdf': report['pdf']['available'],
                      'output': str(folder)}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        (output/'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8048', help='Dedicated instance; never point at an active company instance')
    parser.add_argument('--use-llm', action='store_true')
    parser.add_argument('--require-pdf', action='store_true')
    parser.add_argument('--timeout', type=int, default=2100)
    parser.add_argument('--output', default=str(ROOT/'workspace/deployment-smoke'))
    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
