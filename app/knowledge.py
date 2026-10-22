"""Local mechanism retrieval. No external web search or invented citations."""
import json,re
from pathlib import Path
from docx import Document

def import_knowledge(source:Path, target:Path):
    doc=Document(source); records=[]; category=''; current=None; field=None
    labels={'机理现象':'phenomena','机理原因':'causes','解决措施':'actions','机理规则':'rule_text'}
    for p in doc.paragraphs:
        text=p.text.strip()
        if not text:continue
        if p.style.name=='Heading 1':category=text
        elif p.style.name=='Heading 2':
            current={'id':f'KB-{len(records)+1:03d}','category':category,'fault':text,
                     'source':source.name,'section':f'{category} / {text}',
                     'phenomena':'','causes':'','actions':'','rule_text':''}
            records.append(current);field=None
        elif current:
            hit=next((k for k in labels if text.startswith(k)),None)
            if hit:field=labels[hit];text=text[len(hit):].lstrip('：: ')
            if field:current[field]+=('\n' if current[field] else '')+text
    if not records:raise ValueError('文档未识别到故障章节，请采用带一级/二级标题的知识文档')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return records

def retrieve(records,category='电动机'):
    # The first document is small: exact equipment filter has better traceability than opaque vector ranking.
    found=[r for r in records if r['category']==category]
    return found[:4]
