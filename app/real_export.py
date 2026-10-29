"""Expand retained DOCX components; preserve fonts, styles, page system and opaque parts."""
from copy import deepcopy
import hashlib
from zipfile import ZipFile
from lxml import etree

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
NS={'w':W,'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}


def export_real(reference,s,a,decision,text,out,knowledge,writer):
    from .export import replace_text
    if hashlib.sha256(reference.read_bytes()).hexdigest()!='3dea2931998ac6034e9f1122aae644e7860e53aa075ebd0fc45a2615b758c402':
        raise ValueError('参考报告模板版本不匹配')
    with ZipFile(reference) as src:
        root=etree.fromstring(src.read('word/document.xml'))
        body=root.find('{'+W+'}body')
        ps=body.findall('{'+W+'}p');tables=body.findall('{'+W+'}tbl')
        section=deepcopy(body.find('{'+W+'}sectPr'))
        width=int(section.find('{'+W+'}pgSz').get('{'+W+'}w'))-sum(int(section.find('{'+W+'}pgMar').get('{'+W+'}'+k,'0')) for k in ['left','right','gutter'])
        rels=etree.fromstring(src.read('word/_rels/document.xml.rels'))
        extra={}
        reader=a.get('report_plan',{}).get('version')=='reader_report_v3'
        for child in list(body):body.remove(child)

        def paragraph(value,role=4,keep=False):
            p=deepcopy(ps[role])
            for node in p.xpath('.//w:bookmarkStart|.//w:bookmarkEnd',namespaces=NS):node.getparent().remove(node)
            replace_text(p,str(value))
            prop=p.find('{'+W+'}pPr')
            if prop is None:prop=etree.SubElement(p,'{'+W+'}pPr')
            for br in prop.findall('{'+W+'}pageBreakBefore'):prop.remove(br)
            if keep:
                for tag in ['keepNext','keepLines']:
                    node=prop.find('{'+W+'}'+tag)
                    if node is None:node=etree.SubElement(prop,'{'+W+'}'+tag)
                    node.set('{'+W+'}val','1')
            body.append(p)
            return p

        def heading(n,title):
            p=paragraph(f'{n:02d}  {title}',2,True)
            nodes=p.xpath('.//w:t',namespaces=NS)
            if len(nodes)>=2:
                nodes[0].text=f'{n:02d}  '
                nodes[1].text=title
                for node in nodes[2:]:node.text=''

        def table(rows,widths,header=True,label_columns=(0,),merge_last=False):
            # Derive properties and font-bearing paragraphs from the supplied template cells.
            template=tables[0];tr0=template.find('{'+W+'}tr');cells=tr0.findall('{'+W+'}tc')
            tbl=etree.Element('{'+W+'}tbl');props=deepcopy(template.find('{'+W+'}tblPr'));tbl.append(props)
            tw=props.find('{'+W+'}tblW');tw.set('{'+W+'}w',str(width));tw.set('{'+W+'}type','dxa')
            grid=etree.SubElement(tbl,'{'+W+'}tblGrid')
            for val in widths:etree.SubElement(grid,'{'+W+'}gridCol').set('{'+W+'}w',str(val))
            for ri,values in enumerate(rows):
                tr=etree.SubElement(tbl,'{'+W+'}tr');pr=etree.SubElement(tr,'{'+W+'}trPr');etree.SubElement(pr,'{'+W+'}cantSplit')
                if ri==0 and header:etree.SubElement(pr,'{'+W+'}tblHeader')
                for ci,(value,cw) in enumerate(zip(values,widths)):
                    if merge_last and ri==len(rows)-1 and ci>=2:continue
                    tc=deepcopy(cells[0 if (ri==0 and header) or ci in label_columns else 1])
                    tcpr=tc.find('{'+W+'}tcPr')
                    tcpr.find('{'+W+'}tcW').set('{'+W+'}w',str(cw))
                    for span in tcpr.findall('{'+W+'}gridSpan'):tcpr.remove(span)
                    if merge_last and ri==len(rows)-1 and ci==1:
                        tcpr.find('{'+W+'}tcW').set('{'+W+'}w',str(sum(widths[1:])))
                        etree.SubElement(tcpr,'{'+W+'}gridSpan').set('{'+W+'}val',str(len(widths)-1))
                    p=tc.find('{'+W+'}p');replace_text(p,str(value))
                    pp=p.find('{'+W+'}pPr')
                    if pp is None:pp=etree.SubElement(p,'{'+W+'}pPr')
                    if ri<len(rows)-1:etree.SubElement(pp,'{'+W+'}keepNext')
                    for other in list(tc):
                        if other is not p and other is not tcpr:tc.remove(other)
                    tr.append(tc)
            body.append(tbl)
            paragraph('',1)

        image_proto=next(p for p in ps if p.xpath('.//a:blip',namespaces=NS))
        def chart(ch):
            p=deepcopy(image_proto)
            prop=p.find('{'+W+'}pPr')
            if prop is None:prop=etree.SubElement(p,'{'+W+'}pPr')
            for tag in ['keepNext','keepLines']:
                node=prop.find('{'+W+'}'+tag)
                if node is None:node=etree.SubElement(prop,'{'+W+'}'+tag)
                node.set('{'+W+'}val','1')
            image_id=100+len(extra)
            rid=f'rIdRealImage{image_id}'
            for node in p.xpath('.//a:blip',namespaces=NS):node.set('{'+R+'}embed',rid)
            for node in p.xpath('.//wp:docPr',namespaces=NS):
                node.set('id',str(image_id));node.set('name',ch['title']);node.set('descr',ch['title']+'，来源'+ch['source'])
            for node in p.xpath('.//wp:extent|.//a:xfrm/a:ext',namespaces=NS):
                node.set('cx',str(width*635));node.set('cy',str(round(width*635*(3.3 if reader else 3.65)/9.5)))
            body.append(p)
            name='real_'+ch['file'];extra['word/media/'+name]=(out/ch['file']).read_bytes()
            etree.SubElement(rels,'{'+REL+'}Relationship',Id=rid,Type=R+'/image',Target='media/'+name)
            if reader:
                explanation=next(x for x in text['chart_explanations'] if x['dataset_id']==ch['dataset_id'])
                explanation_p=paragraph('机理含义  '+explanation['text'],3)
                explanation_pr=explanation_p.find('{'+W+'}pPr')
                for node in explanation_pr.findall('{'+W+'}keepNext'):explanation_pr.remove(node)
                etree.SubElement(explanation_pr,'{'+W+'}keepLines')
            else:
                paragraph(ch['dataset_id']+' · 来源 '+ch['source']+'；单位 '+ch['unit']+'；按原始坐标绘制。',1)

        device=s['device']
        matching=decision.get('profile')=='mechanism_matching_v2'
        if reader:
            plan=a['report_plan']
            paragraph(device['name']+'状态分析报告',0)
            subtitle=device.get('region_name') or device['location']
            if decision.get('trend_start') and decision.get('trend_end'):
                subtitle+='  |  数据时间区间 '+decision['trend_start'][:10]+' 至 '+decision['trend_end'][:10]
            paragraph(subtitle,1)
            number=0
            def section_heading(title):
                nonlocal number
                number+=1
                heading(number,title)
            section_heading('结论摘要')
            paragraph('当前状态  '+plan['conclusion'],3)
            paragraph(text['mechanism'])
            section_heading('设备与数据范围')
            table([['设备名称',device['name'],'安装区域',device.get('region_name') or device.get('location') or '未提供'],
                   ['设备编码',device.get('device_code') or '未提供','监测部位',device.get('measure_point_name') or '未提供'],
                   ['采集工况',a.get('acquisition_status',{}).get('label','未统计')+'（记录占比）','','']],
                  [width*18//100,width*24//100,width*16//100,width-width*58//100],header=False,label_columns=(0,2),merge_last=True)
            for kind,label in [('trend','振动趋势'),('waveform','时域波形'),('spectrum','幅值频谱')]:
                charts=[ch for ch in a['chart_manifest'] if ch['kind']==kind]
                if not charts:continue
                section_heading(label)
                for ch in charts:chart(ch)
            section_heading('综合判定')
            paragraph('当前判定  '+text['assessment'],3)
            section_heading('检维修措施')
            paragraph('01 现场复核  '+text['action1'],25)
            paragraph('02 检修闭环  '+text['action2'],26)
            section_heading('参考源')
            references={}
            for k in knowledge:
                if k['id'] in text['citations']:
                    references.setdefault(k['source'],[]).append('['+k['id']+'] '+k['section'])
            for source,entries in references.items():
                paragraph('来源文件  '+source,1)
                paragraph('引用条目  '+'；'.join(entries),1)
            if not text['citations']:paragraph('本次未引用具体机理条目。',1)
        else:
            title=device['component']+device['point_name']+'状态分析报告'
            paragraph(title,0)
            paragraph(device['location']+' / '+device['name'],1)
            heading(1,'结论摘要')
            paragraph('当前状态  '+decision['state'],3)
            paragraph(a['summary'])
            paragraph(('模型分析  ' if writer.get('mode')=='llm' else '固定说明  ')+text['mechanism'],3)
            heading(2,'设备与数据范围')
            status=a.get('acquisition_status',{})
            table([['设备名称',device['name'],'安装区域',device.get('region_name') or device.get('location') or '未提供'],
                   ['设备编码',device.get('device_code') or '未提供','监测部位',device.get('measure_point_name') or '未提供'],
                   ['采集工况',status.get('label','未统计'),'','']],
                  [width*18//100,width*24//100,width*16//100,width-width*58//100],header=False,label_columns=(0,2),merge_last=True)
            paragraph('采集工况：速度有效值>0.2 mm/s为运行，≤0.2 mm/s为停机；按记录数统计，非运行时长占比。'+
                      (f"共{status['total']}条，运行{status['running_count']}条、停机{status['stopped_count']}条。" if status.get('available') else '未提供速度有效值，无法统计。'),1)
            for warning in a['warnings']:paragraph('核查提示  '+warning,7)
            paragraph('数据缺口  '+text['limitations'],7)
            heading(3,'振动趋势')
            paragraph('各项特征按实际采集时间展示，保留不同采集时段的分布。')
            for series in a['series']:
                ch=next((ch for ch in a['chart_manifest'] if ch['dataset_id']==series['dataset_id']),None)
                if ch:chart(ch)
            heading(4,'时域波形')
            for ch in [x for x in a['chart_manifest'] if x['kind']=='waveform']:chart(ch)
            paragraph('采用用户确认的最新波形；按提供的相对时间坐标展示。缺少的采样元数据不从坐标反推，不复算特征。' if s['waveform'] is not None else '未提供波形，不生成替代波形。')
            heading(5,'幅值频谱')
            for ch in [x for x in a['chart_manifest'] if x['kind']=='spectrum']:chart(ch)
            paragraph('采用客户提供的频谱坐标，不执行FFT。倍频表为精确坐标读取，不是主峰或峰值搜索结果；未提供精确坐标时不插值。')
            if a['order_coordinates']:
                table([['阶次','参考频率 Hz','幅值 m/s²','原始行号']]+[[str(x['order'])+'X',str(x['hz']),x['amplitude'] or '无精确坐标',x['source_row'] or '—'] for x in a['order_coordinates']],
                      [width*12//100,width*23//100,width*45//100,width-width*80//100])
            paragraph('按用户确认的业务口径，频谱对应频率的纵坐标作为倍频幅值，能量和按纵坐标相加；与速度有效值的输入数值相除，不进行单位转换，不称为无量纲物理能量比。' if matching else '加速度谱幅值与速度有效值的物理量及单位不同，且采集关联未确认，不直接相除套用机理比值。')
            heading(6,'综合判定')
            paragraph('当前判定  '+decision['state'],3)
            if matching:
                paragraph('全部历史记录按时间对齐后逐次匹配，结果如下。')
                for rule in decision['rules']:
                    paragraph(rule['name']+'：'+rule['status'],3,True)
                    paragraph(rule['detail'])
                    if 'records' not in rule:continue
                    paragraph('来源 '+rule['knowledge_id']+' / '+rule['source'],1)
                    table([['条件','满足/总次数','不满足','未知']]+[[c['name'],str(c['matched'])+'/'+str(c['total']),str(c['failed']),str(c['unknown'])] for c in rule['condition_summary']],
                          [width*61//100,width*15//100,width*12//100,width-width*88//100])
                    for label,row in [('最近匹配',rule.get('latest_assessment')),('历史最高匹配',rule.get('best'))]:
                        if row is None:continue
                        paragraph(label+' '+str(row['time'])+'；满足'+str(row['matched'])+'/'+str(row['total'])+'项，不满足'+str(row['failed'])+'项，未知'+str(row['unknown'])+'项；'+row['support'],7)
                        if label=='历史最高匹配' and row==rule.get('latest_assessment'):
                            paragraph('与最近匹配为同一记录。',1);continue
                        table([['条件','原值或比值','结果']]+[[c['name'],c['value'] or '—',c['status']] for c in row['conditions']],
                              [width*53//100,width*34//100,width-width*87//100])
                paragraph('全部逐时刻条件结果、计算表达式、参与原值和来源行号见网页“下载全部逐时刻匹配明细CSV”，并归档于rule_matches.csv。',1)
            else:
                for rule in decision['rules']:paragraph(rule['name']+'：'+rule['status']+'。'+rule['detail'])
            evidence={e['id']:e for e in a['evidence_items']}
            for h in text.get('hypotheses',[]):
                paragraph('待核查方向  '+h['fault'],3)
                paragraph(h['explanation'])
                for label,key in [('支持依据','supporting_evidence'),('矛盾或限制依据','conflicting_evidence')]:
                    for eid in h[key]:
                        e=evidence[eid];value=e.get('y',e.get('amplitude'))
                        paragraph(label+'  '+eid+' '+e['name']+' '+str(value)+' '+e['unit']+'；'+e['file']+' 原始行 '+str(e.get('source_row')),1)
                paragraph('待补条件  '+'；'.join(h['missing_evidence']),7)
                paragraph('机理引用  '+'、'.join(h['knowledge_ids']),1)
            if not text.get('hypotheses') and not matching:paragraph('本次未形成带完整证据引用的故障假设。固定模板不替代模型或专业诊断。')
            heading(7,'检维修措施')
            paragraph('01 现场复核  '+text['action1'],25)
            paragraph('02 检修闭环  '+text['action2'],26)
            heading(8,'参考源与编制记录')
            if matching:
                paragraph('判定口径：各条件等权，满足率为满足条件数占总条件数的比例，不代表故障概率或严重程度。各历史时刻共用最新频谱作为参考，不代表当时实测频谱。运行状态、方向及负载不作为本次规则的前置条件。',1)
            paragraph('台账、数值、规则条件、故障方向和支持等级由程序生成；模型只撰写解释与建议。机理知识的典型现象不等同于本次实测事实。' if matching else '确定性内容来自案例包及独立规则；“模型分析”、待核查方向和措施为模型撰写，需复核后使用。知识文档的典型现象不等同于本次实测事实。')
            for k in knowledge:
                if k['id'] in text['citations'] or any(r.get('knowledge_id')==k['id'] for r in decision['rules']):paragraph('['+k['id']+'] '+k['source']+' / '+k['section'],1)
            paragraph('编制方式  '+writer['message'],7)
            paragraph('知识条目全部载入，未静默截断；全部历史记录由程序逐项匹配。模型接收每条件的次数统计、最近与历史最高匹配记录和来源，不以首末值替代规则计算，不接收图像。' if matching else '知识条目全部载入，未静默截断；模型只接收历史首末值、记录数、来源、倍频坐标与检查结果，不接收全量曲线或图像。',1)
            paragraph('输入与报告对应',3)
            for d in s['datasets']:paragraph(d['dataset_id']+' '+d['name']+' → '+('03 振动趋势' if d['kind']=='trend' else '04 时域波形' if d['kind']=='waveform' else '05 幅值频谱')+'；'+d['data_file']+'；共'+str(len(d['rows']))+'条；保留source_row。',1)
            paragraph('完整数据缺口与限制',3)
            paragraph('；'.join(a['missing']),1)
        body.append(section)
        updates={'word/document.xml':etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True),
                 'word/_rels/document.xml.rels':etree.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)}
        for item in src.infolist():
            if item.filename.startswith(('word/header','word/footer')) and item.filename.endswith('.xml'):
                part=etree.fromstring(src.read(item.filename))
                for p in part.xpath('//w:p',namespaces=NS):
                    old=''.join(p.xpath('.//w:t/text()',namespaces=NS))
                    if '示例报告' in old or '模拟数据' in old:replace_text(p,'设备状态报告')
                    if 'RPT-0001' in old:replace_text(p,'报告 '+out.name+' | 设备 '+(device.get('device_code') or device['id']))
                updates[item.filename]=etree.tostring(part,xml_declaration=True,encoding='UTF-8',standalone=True)
        with ZipFile(out/'report.docx','w') as dest:
            for item in src.infolist():dest.writestr(item,updates.get(item.filename,src.read(item.filename)))
            for name,raw in extra.items():dest.writestr(name,raw)
    return text['mechanism'] if reader else a['summary']
