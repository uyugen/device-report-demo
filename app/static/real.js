/* Customer-final-value reports, with source rows and explicit acquisition boundaries. */
function realHistoryTable(series) {
  return `<div class="table-scroll"><table><thead><tr><th>历史特征</th><th>单位</th><th class="numeric">历史首值</th><th class="numeric">历史末值</th></tr></thead><tbody>${series.map(s=>`<tr><td>${esc(s.name)}</td><td class="unit">${esc(s.unit)}</td><td class="numeric">${esc(s.first.y)}</td><td class="numeric">${esc(s.last.y)}</td></tr>`).join('')}</tbody></table></div>`;
}
function realCasePreview(data, archived) {
  const series=data.series || [],charts=data.chart_manifest || [];
  const panel=$('case-preview');panel.hidden=false;
  panel.innerHTML=`<h2>数据检查信息</h2><span class="case-title">${esc(data.title)}${archived?' · 报告关联案例':''}</span>
    <dl class="case-meta"><dt>数据性质</dt><dd><span class="tag tag-success">真实采集</span></dd>
    <dt>设备</dt><dd>${esc(data.device.name)}</dd><dt>部位 / 测点</dt><dd>${esc(data.device.component)} / ${esc(data.device.point_name)}</dd>
    <dt>转速</dt><dd class="numeric">${data.device.rpm ? esc(data.device.rpm)+' r/min':'未提供'}</dd>
    <dt>转频参考</dt><dd class="numeric">${data.device.rpm ? esc(data.device.rpm/60)+' Hz':'未提供'}</dd>
    <dt>历史特征</dt><dd>${series.length} 类 / ${series.reduce((n,s)=>n+s.count,0)} 条</dd>
    <dt>最新图谱</dt><dd>${data.has_waveform?'波形已提供':'波形未提供'} / ${data.has_spectrum?'频谱已提供':'频谱未提供'}</dd>
    <dt>采集时间</dt><dd>${esc(data.measurement?.measured_time || '未提供绝对时间')}</dd>
    <dt>图表</dt><dd>${charts.length} 张，使用原始坐标</dd></dl>
    <div class="case-check ${data.warnings.length?'has-warning':''}">输入结构已通过 · ${data.warnings.length?'存在待核查信息':'未发现结构错误'}</div>
    ${warnings(data.warnings)}
    <details class="accordion"><summary>分析限制（${data.limitations.length} 项）</summary><div class="accordion-body">${data.limitations.map(x=>`<p>${esc(x)}</p>`).join('')}</div></details>
    <details class="accordion"><summary>历史特征首末值</summary><div class="accordion-body">${realHistoryTable(series)}<p class="hint">历史末值未绑定最新图谱，不当作当前特征。</p></div></details>
    <p class="hint">直接使用客户提供的特征与频谱，不复算信号。</p>`;
}
function renderReal(data) {
  const a=data.analysis,base=`/api/reports/${encodeURIComponent(data.id)}/files/`;
  const section=(n,title,body)=>`<section class="report-section"><h3><span>${n}</span>${title}</h3>${body}</section>`;
  const chart=ch=>`<figure class="source-figure"><figcaption>${esc(ch.title)} <span class="caption">${esc(ch.dataset_id)}</span></figcaption><img src="${base+encodeURIComponent(ch.file)}" alt="真实采集数据 ${esc(ch.title)}" loading="lazy"><p class="caption">来源 ${esc(ch.source)} · 单位 ${esc(ch.unit)} · 按原始坐标绘制</p></figure>`;
  const refs=data.text.citations || [];
  const ev=Object.fromEntries(a.evidence_items.map(e=>[e.id,e]));
  const evidenceLink=id=>{const e=ev[id];return e?`<p class="caption"><span class="numeric">${esc(id)}</span> ${esc(e.name)}：<span class="numeric">${esc(e.y ?? e.amplitude)} ${esc(e.unit)}</span>；${esc(e.file)}，原始行 ${esc(e.source_row)}${e.x?'，'+esc(e.x):''}</p>`:'';};
  const hypotheses=(data.text.hypotheses || []).map(h=>`<div class="rule-row"><span class="tag tag-warning">待核查</span><strong>${esc(h.fault)}</strong><p>${esc(h.explanation)}</p><p class="caption">支持依据</p>${h.supporting_evidence.map(evidenceLink).join('')}${h.conflicting_evidence.length?'<p class="caption">矛盾或限制依据</p>'+h.conflicting_evidence.map(evidenceLink).join(''):''}<p>待补条件：${esc(h.missing_evidence.join('；') || '仍需现场验证')}</p><p class="citation">机理引用：${h.knowledge_ids.map(esc).join('、')}</p></div>`).join('');
  const orders=a.order_coordinates.length?`<div class="table-scroll"><table><thead><tr><th>阶次</th><th class="numeric">参考频率 Hz</th><th class="numeric">加速度幅值 m/s²</th><th>原始行号</th></tr></thead><tbody>${a.order_coordinates.map(x=>`<tr><td>${x.order}X</td><td class="numeric">${esc(x.hz)}</td><td class="numeric">${x.amplitude===null?'无精确坐标':esc(x.amplitude)}</td><td class="numeric">${esc(x.source_row || '—')}</td></tr>`).join('')}</tbody></table></div>`:'';
  const facts=`<div class="table-scroll"><table class="facts"><tbody>${[
    ['设备',data.device.name],['设备编号',data.device.id],['部位 / 测点',data.device.component+' / '+data.device.point_name],
    ['测点方向',data.device.direction+'（实际方向待确认）'],['转速',data.device.rpm?data.device.rpm+' r/min':'未提供'],
    ['工况',data.device.load || '未提供'],['特征与图谱','未确认同一次采集，分别展示'],['严重程度',data.decision.severity]
  ].map(([k,v])=>`<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div>
  <p class="feature-source">数值为客户提供的最终值，保留原始文本。设备名称“模拟机械臂”为源台账原文，数据性质为真实采集。</p>${realHistoryTable(a.series)}
  <details><summary>数据缺口与分析限制（${a.missing.length} 项）</summary><div class="accordion-body">${a.missing.map(v=>`<p>${esc(v)}</p>`).join('')}</div></details>`;
  const rules=data.decision.rules.map(r=>`<div class="rule-row"><span class="tag tag-warning">${esc(r.status)}</span><strong>${esc(r.name)}</strong><p>${esc(r.detail)}</p><p class="citation">${esc(r.source)}</p></div>`).join('');
  const correspondence=`<div class="table-scroll"><table><thead><tr><th>输入</th><th>报告位置</th><th>数据来源</th></tr></thead><tbody>${a.chart_manifest.map(ch=>`<tr><td>${esc(ch.dataset_id)} ${esc(ch.title)}</td><td>${ch.kind==='trend'?'03 振动趋势':ch.kind==='waveform'?'04 时域波形':'05 幅值频谱'}</td><td>${esc(ch.source)}</td></tr>`).join('')}</tbody></table></div>`;
  $('empty').hidden=true;$('report').hidden=false;$('report-state').textContent='真实数据报告';
  $('downloads').innerHTML=`${data.pdf.available?`<a class="button primary" href="${base}report.pdf" target="_blank" rel="noopener">查看 PDF</a>`:''}<a class="button" href="${base}report.docx">下载 Word</a><a class="text-link" href="${base}evidence.json" target="_blank" rel="noopener">依据</a><a class="text-link" href="${base}writer_input.json" target="_blank" rel="noopener">写作输入</a>`;
  $('report').innerHTML=`<header class="report-header"><span class="stamp">真实采集数据</span><h1>${esc(data.device.component+data.device.point_name)}状态分析报告</h1><div class="report-location">${esc(data.device.location)} / ${esc(data.device.name)}</div><div class="meta">最新图谱绝对时间：${esc(data.measured_time || '未提供')} · 历史特征与最新图谱未绑定</div></header>
    <section class="conclusion"><h3><span>01</span>结论摘要</h3><strong>${esc(data.decision.state)}</strong><p>${esc(data.summary)}</p><p><strong>${data.writer.mode==='llm'?'模型分析':'固定说明'}：</strong>${esc(data.text.mechanism)}</p></section>${warnings(a.warnings)}
    ${section('02','设备与数据范围',facts)}
    ${section('03','振动趋势','<p class="caption">全部历史数据按原始坐标展示，不补算趋势增幅。历史末值不等同于最新图谱的当前值。</p>'+a.chart_manifest.filter(ch=>ch.kind==='trend').map(chart).join(''))}
    ${section('04','时域波形',a.chart_manifest.filter(ch=>ch.kind==='waveform').map(chart).join('') || '<p>未提供波形。</p>')}
    ${section('05','幅值频谱',a.chart_manifest.filter(ch=>ch.kind==='spectrum').map(chart).join('')+orders+'<p class="caption">倍频表为精确坐标读取，不是峰值搜索；不插值，不推断全谱主峰。加速度谱与速度有效值不直接相除套用机理条件。</p>')}
    ${section('06','综合判定',`<p>${esc(data.text.limitations)}</p>${hypotheses || '<p>本次未形成带完整证据引用的故障假设。</p>'}<details><summary>独立规则执行记录</summary>${rules}</details>`)}
    ${section('07','检维修措施',`<p><strong>现场复核：</strong>${esc(data.text.action1)}</p><p><strong>检修闭环：</strong>${esc(data.text.action2)}</p>`)}
    ${section('08','参考源与编制记录',`<p class="caption">确定性内容为台账、数值、坐标和独立规则结果；模型内容为机理分析、待核查方向与建议，需人工复核。</p>${data.knowledge.filter(k=>refs.includes(k.id)).map(k=>`<p class="citation">[${esc(k.id)}] ${esc(k.source)} / ${esc(k.section)}</p>`).join('')}<p class="caption">${esc(data.writer.message)}</p><p class="caption">全部 ${data.knowledge.length} 条知识载入写作上下文；模型接收每组历史首末值、记录数及来源，不接收全量历史曲线或图像。</p>${correspondence}<p class="caption">报告编号 ${esc(data.id)}${data.pdf.available?'':'；PDF未生成：'+esc(data.pdf.reason)}</p>`)} `;
}
