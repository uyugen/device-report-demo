"""Check deployment assets without changing application state or disclosing secrets."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_HASH = '3dea2931998ac6034e9f1122aae644e7860e53aa075ebd0fc45a2615b758c402'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-pdf', action='store_true')
    args = parser.parse_args()
    errors = []

    def check(name, ok, detail='', required=True):
        print(f'{"PASS" if ok else "FAIL" if required else "WARN"} {name}: {detail}')
        if not ok and required:
            errors.append(name)

    check('Python', sys.version_info >= (3, 10), sys.version.split()[0] + '; recommended 3.11 or 3.12')
    modules = ['fastapi', 'uvicorn', 'langgraph', 'numpy', 'scipy', 'matplotlib',
               'docx', 'httpx', 'dotenv', 'multipart']
    imports_ready = True
    for module in modules:
        ok = importlib.util.find_spec(module) is not None
        check('dependency ' + module, ok)
        imports_ready &= ok
    template = ROOT / 'inputs/reference.docx'
    check('Word template', template.exists() and hashlib.sha256(template.read_bytes()).hexdigest() == TEMPLATE_HASH,
          'inputs/reference.docx')
    manifest_path = ROOT / 'examples/manifest.json'
    check('Example manifest', manifest_path.is_file())
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for item in [manifest['knowledge'], *manifest['cases']]:
            path = ROOT / 'examples' / item['file']
            check('example ' + item['file'], path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'])
        if imports_ready:
            sys.path.insert(0, str(ROOT))
            from app.knowledge import import_knowledge
            from app.case_data import parse_zip, check_snapshot
            from app.signal_data import analyse
            from app.mechanism_rules import match_rules
            rules = json.loads((ROOT / 'config/rules.json').read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory(prefix='device-report-check-') as folder:
                records = import_knowledge(ROOT/'examples'/manifest['knowledge']['file'], Path(folder)/'knowledge.json')
                check('knowledge count', len(records) == manifest['knowledge']['count'])
                for item in manifest['cases']:
                    try:
                        snap = parse_zip((ROOT/'examples'/item['file']).read_bytes())
                        snap['quality'] = check_snapshot(snap)
                        decision = match_rules(snap, analyse(snap), rules, records)
                        ok = (decision['overall_status'] == item['expected_status']
                              and sorted(c['fault'] for c in decision['candidates']) == sorted(item['expected_faults'])
                              and decision['historical_status_counts'].get('故障', 0) == item['history_fault']
                              and decision['historical_status_counts'].get('正常', 0) == item['history_normal']
                              and len(decision['rules']) == 4
                              and all(r.get('record_count') == 24 and r.get('complete_count') == 24 for r in decision['rules']))
                        check('case rules ' + item['file'], ok, decision['state'])
                    except Exception as exc:
                        check('case rules ' + item['file'], False, type(exc).__name__ + ': ' + str(exc))
    check('LibreOffice', bool(shutil.which('libreoffice')), 'required for PDF', args.require_pdf)
    font = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    check('Chinese chart font', font.exists(), str(font), args.require_pdf)
    check('.env', (ROOT/'.env').is_file(), 'optional for fixed-text mode; credentials are never printed', False)
    print(f'\nRequired failures: {len(errors)}')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
