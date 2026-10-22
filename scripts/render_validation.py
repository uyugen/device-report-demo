"""Render the four acceptance reports with the retained QA renderer."""
import json
import subprocess
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
results=json.loads((ROOT/'workspace/qa/upload_validation.json').read_text())
for item in results:
    dest=ROOT/'workspace/qa/upload_render'/item['sample']
    subprocess.run([sys.executable,str(ROOT/'workspace/qa/render_docx.py'),
                    str(ROOT/'workspace'/item['id']/'report.docx'),'--output_dir',str(dest),'--emit_pdf'],check=True)
    print(item['sample'],len(list(dest.glob('page-*.png'))),'pages',flush=True)
