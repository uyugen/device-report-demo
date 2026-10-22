"""Local mechanism retrieval. No external web search or invented citations."""
import json,re
from pathlib import Path
from docx import Document

def import_knowledge(source:Path, target:Path, source_name=None):
    doc=Document(source); records=[]; category=''; current=None; field=None
    labels={'机理现象':'phenomena','机理原因':'causes','解决措施':'actions','机理规则':'rule_text'}
    # Preserve text in tables as well as normal paragraphs, in document order.
    paragraphs=[]
    for block in doc.iter_inner_content():
        if hasattr(block,'text'):paragraphs.append(block)
        else:
            for row in block.rows:
                for cell in row.cells:paragraphs.extend(cell.paragraphs)
    for p in paragraphs:
        text=p.text.strip()
        if not text:continue
        if p.style.name=='Heading 1':category=text
        elif p.style.name=='Heading 2':
            if not category:raise ValueError('故障二级标题之前必须有设备类别一级标题')
            current={'id':f'KB-{len(records)+1:03d}','category':category,'fault':text,
                     'source':source_name or source.name,'section':f'{category} / {text}',
                     'phenomena':'','causes':'','actions':'','rule_text':''}
            records.append(current);field=None
        elif current:
            hit=next((k for k in labels if text.startswith(k)),None)
            if hit:field=labels[hit];text=text[len(hit):].lstrip('：: ')
            if field:current[field]+=('\n' if current[field] else '')+text
    if not records:raise ValueError('文档未识别到故障章节，请采用带一级/二级标题的知识文档')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(target)
    return records

def retrieve(records,category=None):
    # Full-document context. Category is retained only for compatibility, never filters.
    return list(records)
