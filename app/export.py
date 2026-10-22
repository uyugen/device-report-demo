"""Patch only document.xml text slots and three media files in the retained DOCX."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import subprocess,tempfile,shutil,hashlib
from copy import deepcopy

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS={'w':W}
def fmt(value,n=3):
    return '未提供' if value is None else f'{value:.{n}f}'
def replace_text(p,text):
    nodes=p.xpath('.//w:t',namespaces=NS)
    if not nodes:
        run=etree.SubElement(p,'{'+W+'}r');nodes=[etree.SubElement(run,'{'+W+'}t')]
    separator=text.find('  ')
    def is_bold(node):
        bold=node.getparent().find('w:rPr/w:b',namespaces=NS)
        return bold is not None and bold.get('{'+W+'}val','true') not in ['0','false','off']
    normal=next((i for i,node in enumerate(nodes) if not is_bold(node)),None)
    if 0<separator<20 and is_bold(nodes[0]) and normal is not None and normal>0:
        for node in nodes:node.text=''
        nodes[0].text=text[:separator]+'  '
        nodes[normal].text=text[separator+2:]
    else:
        nodes[0].text=text
        for node in nodes[1:]:node.text=''

def fill_table(tbl,rows):
    for row,values in zip(tbl.findall('{'+W+'}tr'),rows):
        for cell,value in zip(row.findall('{'+W+'}tc'),values):
            ps=cell.findall('{'+W+'}p')
            if ps:replace_text(ps[0],str(value))
            for p in ps[1:]:replace_text(p,'')

def export_docx(reference,snapshot,analysis,decision,text,out,knowledge=None,writer=None):
    if not Path(reference).exists():raise FileNotFoundError('服务器缺少 inputs/reference.docx')
    if hashlib.sha256(Path(reference).read_bytes()).hexdigest()!='3dea2931998ac6034e9f1122aae644e7860e53aa075ebd0fc45a2615b758c402':raise ValueError('报告模板版本不匹配，请重新核对槽位')
    with ZipFile(reference) as z:
        root=etree.fromstring(z.read('word/document.xml'))
        body=root.find('{'+W+'}body');ps=body.findall('{'+W+'}p');tables=body.findall('{'+W+'}tbl')
        f=analysis['features'];d=snapshot['device'];h=snapshot['history'];dt=snapshot['measured_time'][:10]
        first,last=decision['first'],decision['last'];change=decision['change_percent']
        summary=f'历史有效区间速度有效值由 {fmt(first)} mm/s 变为 {fmt(last)} mm/s，变化 {fmt(change,1)}%。故障类型待核实，严重程度未分级。'
        if analysis.get('warnings'):summary+='存在数据差异，请核查后使用分析结论。'
        waveform_info=f'特征来源：{analysis.get("feature_source","程序计算")}。加速度有效值 {fmt(f.get("acceleration_rms"))} m/s²，峰值 {fmt(f.get("acceleration_peak"))} m/s²，峭度 {fmt(f.get("kurtosis"))}，峰值因子 {fmt(f.get("crest_factor"))}。'
        if snapshot['waveform'] is None:waveform_info+='未提供波形，以上为上传值，未复算。'
        else:waveform_info+=f'采样 {snapshot["sampling_rate"]:g} Hz，时长 {snapshot["duration_seconds"]:g} s。'
        peaks='、'.join(f'{p["hz"]:g} Hz' for p in analysis['peaks'][:2])
        spectrum_info=f'显示 0–500 Hz 加速度峰值幅度谱；主要峰值：{peaks}。' if peaks else '未提供当前波形，无法计算当前频谱。'
        spectrum_info+=(f'模拟转速为 {d["rpm"]:g} r/min；阶次判断须关联相同采集窗口。' if analysis['rpm_available'] else '缺少可信转速，不作转频阶次标注。')
        missing='；'.join(analysis['missing']) or '未发现已检查项目的数据缺失'
        slots={0:d['name']+d['component']+'状态分析报告',
          1:f'{d["location"]} / {d["name"]} | 数据截至 {dt} | 模拟数据 仅用于功能演示',
          3:'当前状态  '+decision['state'],4:summary,
          7:'数据缺口  '+missing,
          12:'趋势判断  '+next((r['detail'] for r in decision['rules'] if r.get('kind')=='demo_trend'),'未配置趋势规则')+'。演示阈值不构成行业分级依据。',
          14:waveform_info,16:'机理含义  '+text['mechanism'],18:spectrum_info,
          20:'证据限制  '+text['limitations'],
          23:'当前判定  '+decision['state']+'。'+text['limitations'],
          25:'01 现场复核  '+text['action1'],26:'02 检修闭环  '+text['action2']}
        for i,value in slots.items():replace_text(ps[i],value)
        fill_table(tables[0],[['设备',d['name'],'安装区域',d['location']],
            ['监测部位',d['component'],'测点方向',d['direction']],
            ['采集工况',d['load'],'报告等级','未分级（模拟数据）']])
        for idx,key,label,unit in [(1,'velocity_rms','速度有效值',' mm/s'),(2,'acceleration_rms','加速度有效值',' m/s²')]:
            a,b=h[0][key],h[-1][key]
            fill_table(tables[idx],[['特征名称',label],['起始值',fmt(a)+unit,'历史末值',fmt(b)+unit],
                ['区间变化',(fmt((b-a)/a*100,1)+'%') if a and b is not None else '无法计算','时间范围',h[0]['measured_time'][:10]+' 至 '+dt]])
        fill_table(tables[3],[['来源文件','上传模拟案例及已导入机理文档','引用位置','、'.join(text['citations']) or '未引用特定知识条目']])
        def insert_after(anchor,content):
            p=deepcopy(ps[7] if '  ' in content[:20] else ps[4]);replace_text(p,content);anchor.addnext(p);return p
        anchor=ps[7]
        for warning in analysis.get('warnings',[]):anchor=insert_after(anchor,'核查提示  '+warning)
        # Full current feature table with separate uploaded and recomputed values.
        tbl=etree.Element('{'+W+'}tbl')
        tblpr=deepcopy(tables[1].find('{'+W+'}tblPr'));tbl.append(tblpr)
        rows=[['当前特征及单位','上传值','波形复算值']]
        labels={'velocity_rms':'速度有效值 mm/s','acceleration_rms':'加速度有效值 m/s²',
                'acceleration_peak':'加速度峰值 m/s²','kurtosis':'峭度 无量纲','skewness':'偏度 无量纲','crest_factor':'峰值因子 无量纲'}
        for key,label in labels.items():rows.append([label,fmt(analysis.get('uploaded_features',{}).get(key)),fmt(analysis.get('recomputed_features',{}).get(key))])
        for values in rows:
            tr=etree.SubElement(tbl,'{'+W+'}tr')
            for value in values:
                tc=etree.SubElement(tr,'{'+W+'}tc');p=etree.SubElement(tc,'{'+W+'}p')
                pr=etree.SubElement(p,'{'+W+'}pPr');spacing=etree.SubElement(pr,'{'+W+'}spacing');spacing.set('{'+W+'}after','50')
                r=etree.SubElement(p,'{'+W+'}r');rp=etree.SubElement(r,'{'+W+'}rPr');size=etree.SubElement(rp,'{'+W+'}sz');size.set('{'+W+'}val','18')
                etree.SubElement(r,'{'+W+'}t').text=value
        anchor.addnext(tbl)
        anchor=tables[3]
        cited=[r for r in (knowledge or []) if r['id'] in text['citations']]
        for r in cited:anchor=insert_after(anchor,f'[{r["id"]}] {r["source"]} / {r["section"]}')
        if writer:anchor=insert_after(anchor,'编制方式  '+writer['message'])
        with ZipFile(out/'report.docx','w') as dest:
            for item in z.infolist():
                payload=z.read(item.filename)
                if item.filename=='word/document.xml':payload=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
                if item.filename.startswith('word/footer') and item.filename.endswith('.xml'):
                    footer=etree.fromstring(payload)
                    for paragraph in footer.xpath('//w:p',namespaces=NS):
                        if 'RPT-0001' in ''.join(paragraph.xpath('.//w:t/text()',namespaces=NS)):
                            replace_text(paragraph,'模拟报告 '+out.name+' | 设备 '+d['id'])
                    payload=etree.tostring(footer,xml_declaration=True,encoding='UTF-8',standalone=True)
                for i,name in enumerate(['trend','waveform','spectrum'],1):
                    if item.filename==f'word/media/image{i}.png':payload=(out/f'{name}.png').read_bytes()
                dest.writestr(item,payload)
    return summary

def export_pdf(out):
    exe=shutil.which('libreoffice')
    if not exe:return {'available':False,'reason':'未安装LibreOffice'}
    try:
        with tempfile.TemporaryDirectory(prefix='device-report-lo-') as profile:
            r=subprocess.run([exe,'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--convert-to','pdf','--outdir',str(out),str(out/'report.docx')],capture_output=True,timeout=75)
        if r.returncode or not (out/'report.pdf').is_file():return {'available':False,'reason':'PDF转换未成功，Word仍可下载'}
        return {'available':True}
    except subprocess.TimeoutExpired:return {'available':False,'reason':'PDF转换超时，Word仍可下载'}
