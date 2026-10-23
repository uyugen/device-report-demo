"""Repair archived feature tables without rerunning diagnosis or model writing.

Default: stage repaired DOCX/PDF copies under workspace/qa/feature_table_fix.
Use --apply after visual review to publish the copies, retaining original files.
"""
from pathlib import Path
from zipfile import ZipFile
import argparse
import json
import os
import re
import shutil
import sys
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.export import feature_table, export_pdf, W, NS


def repair(source,destination):
    with ZipFile(source) as archive:
        root=etree.fromstring(archive.read('word/document.xml'))
        body=root.find('w:body',NS)
        table=next((t for t in body.findall('w:tbl',NS)
                    if t.xpath('w:tr[1]/w:tc[1]//w:t/text()',namespaces=NS)==['当前特征及单位']),None)
        if table is None:return 'no_feature_table'
        section=body.find('w:sectPr',NS)
        width=int(section.find('w:pgSz',NS).get('{'+W+'}w'))
        margins=section.find('w:pgMar',NS)
        width-=sum(int(margins.get('{'+W+'}'+side,'0')) for side in ['left','right','gutter'])
        grid=[int(c.get('{'+W+'}w','0')) for c in table.findall('w:tblGrid/w:gridCol',NS)]
        total=table.find('w:tblPr/w:tblW',NS)
        valid=(len(grid)==3 and min(grid)>0 and sum(grid)==width and total is not None
               and total.get('{'+W+'}type')=='dxa' and total.get('{'+W+'}w')==str(width))
        if valid:
            valid=all([int(c.get('{'+W+'}w','0')) for c in row.findall('w:tc/w:tcPr/w:tcW',NS)]==grid
                      for row in table.findall('w:tr',NS))
        if valid:return 'already_valid'
        rows=[[''.join(cell.xpath('.//w:t/text()',namespaces=NS)) for cell in row.findall('w:tc',NS)]
              for row in table.findall('w:tr',NS)]
        if not rows or any(len(row)!=3 for row in rows):raise ValueError('Unexpected feature table shape')
        body.replace(table,feature_table(rows,width,table.find('w:tblPr',NS)))
        destination.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(destination,'w') as output:
            for item in archive.infolist():
                payload=(etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
                         if item.filename=='word/document.xml' else archive.read(item.filename))
                output.writestr(item,payload)
    return 'repaired'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-id',nargs='+')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    work=ROOT/'workspace'
    ids=args.report_id or sorted(p.parent.name for p in work.glob('*/report.docx'))
    results=[]
    for rid in ids:
        if not re.fullmatch(r'\d{8}_\d{6}_[0-9a-f]{8}',rid):raise ValueError('Invalid report ID')
        source=work/rid;stage=work/'qa/feature_table_fix'/rid
        status=repair(source/'report.docx',stage/'report.docx')
        item={'id':rid,'status':status,'published':False}
        if status=='repaired':
            pdf=export_pdf(stage)
            if not pdf['available']:raise RuntimeError(f'{rid}: {pdf}')
            item['pdf']=True
            if args.apply:
                backup=work/'qa/feature_table_backup'/rid
                backup.mkdir(parents=True,exist_ok=True)
                for name in ['report.docx','report.pdf']:
                    if (source/name).exists() and not (backup/name).exists():shutil.copy2(source/name,backup/name)
                for name in ['report.docx','report.pdf']:
                    temp=source/(name+'.layout-fix.tmp')
                    shutil.copy2(stage/name,temp);os.replace(temp,source/name)
                item['published']=True
        results.append(item);print(json.dumps(item),flush=True)
    dest=work/'qa'/('feature_table_published.json' if args.apply else 'feature_table_staged.json')
    dest.write_text(json.dumps(results,indent=2))


if __name__=='__main__':main()
