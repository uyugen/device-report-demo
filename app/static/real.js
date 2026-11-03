/* Customer-final-value reports, with source rows and explicit acquisition boundaries. */
function realHistoryTable(series) {
  return `<div class="table-scroll"><table><thead><tr><th>历史特征</th><th>单位</th><th class="numeric">记录数</th></tr></thead><tbody>${series.map(s=>`<tr><td>${esc(s.name)}</td><td class="unit">${esc(s.unit)}</td><td class="numeric">${esc(s.count)}</td></tr>`).join('')}</tbody></table></div>`;
}
function mechanismRuleRows(decision,base) {
  const num=value=>value===null||value===undefined?'—':esc(value);
  const rowLabel=row=>`${row.matched}/${row.total}项 · 不满足${row.failed} · 未知${row.unknown} · ${row.support}`;
  const conditions=row=>`<div class="table-scroll"><table><thead><tr><th>条件</th><th>原值或比值</th><th>结果</th><th>输入来源</th></tr></thead><tbody>${row.conditions.map(c=>`<tr><td>${esc(c.name)}</td><td class="numeric">${num(c.value)}${c.expression?'<br><small>'+esc(c.expression)+'</small>':''}</td><td>${esc(c.status)}</td><td>${c.sources.map(s=>`${esc(s.file)} 行${esc(s.source_row)}：${esc(s.value)} ${esc(s.unit)}`).join('<br>')}${c.reason?'<br>'+esc(c.reason):''}</td></tr>`).join('')}</tbody></table></div>`;
  return `<p class="caption">全部历史记录按时间对齐后逐次匹配，结果如下。</p><p><a class="text-link" href="${base}rule_matches.csv">下载全部逐时刻匹配明细 CSV</a></p>`+decision.rules.map(r=>{
    if(!r.records)return `<div class="rule-row"><strong>${esc(r.name)}</strong><p>${esc(r.status)}：${esc(r.detail)}</p></div>`;
    const current=r.latest_assessment;
    const summary=`<div class="table-scroll"><table><thead><tr><th>条件</th><th>满足次数</th><th>不满足</th><th>未知</th></tr></thead><tbody>${r.condition_summary.map(c=>`<tr><td>${esc(c.name)}</td><td class="numeric">${c.matched}/${c.total}</td><td class="numeric">${c.failed}</td><td class="numeric">${c.unknown}</td></tr>`).join('')}</tbody></table></div>`;
    const best=r.best;
    return `<div class="rule-row"><strong>${esc(r.fault)}</strong> <span class="tag ${r.status==='正常'?'tag-success':'tag-warning'}">${esc(r.status)}</span><p>${esc(r.detail)}</p><p class="citation">${esc(r.knowledge_id)} · ${esc(r.source)}</p>${summary}
      ${current?`<details class="accordion"><summary>最近记录 ${esc(current.time)} · ${esc(rowLabel(current))}</summary><div class="accordion-body">${conditions(current)}</div></details>`:''}
      ${best?`<details class="accordion"><summary>历史最高匹配 ${esc(best.time)} · ${esc(rowLabel(best))}</summary><div class="accordion-body">${conditions(best)}</div></details>`:''}
      <details class="accordion"><summary>全部 ${r.records.length} 次匹配记录</summary><div class="accordion-body"><p class="caption">点击各时刻查看条件数值和来源。最近匹配与历史最高匹配分别报告。</p>${r.records.map(row=>`<details><summary>${esc(row.time)} · ${esc(rowLabel(row))}</summary>${conditions(row)}</details>`).join('')}</div></details></div>`;
  }).join('');
}
function realCasePreview(data, archived) {
  const series=data.series || [],charts=data.chart_manifest || [];
  const panel=$('case-preview');panel.hidden=false;
  panel.innerHTML=`<h2>数据检查信息</h2><span class="case-title">${esc(data.title)}${archived?' · 报告关联案例':''}</span>
    <dl class="case-meta"><dt>数据性质</dt><dd><span class="tag tag-success">真实采集</span></dd>
    <dt>设备</dt><dd>${esc(data.device.name)}</dd><dt>部位 / 测点</dt><dd>${esc(data.device.component)} / ${esc(data.device.point_name)}</dd>
    <dt>监测部位</dt><dd>${esc(data.device.measure_point_name || '未提供')}</dd>
    <dt>采集工况</dt><dd>${esc(data.acquisition_status?.label || '未统计')}</dd>
    <dt>转速</dt><dd class="numeric">${data.device.rpm ? esc(data.device.rpm)+' r/min':'未提供'}</dd>
    <dt>转频参考</dt><dd class="numeric">${data.device.rpm ? esc(data.device.rpm/60)+' Hz':'未提供'}</dd>
    <dt>历史特征</dt><dd>${series.length} 类 / ${series.reduce((n,s)=>n+s.count,0)} 条</dd>
    <dt>最新图谱</dt><dd>${data.has_waveform?'波形已提供':'波形未提供'} / ${data.has_spectrum?'频谱已提供':'频谱未提供'}</dd>
    <dt>采集时间</dt><dd>${esc(data.measurement?.measured_time || '未提供绝对时间')}</dd>
    <dt>图表</dt><dd>${charts.length} 张，使用原始坐标</dd></dl>
    <div class="case-check ${data.warnings.length?'has-warning':''}">输入结构已通过 · ${data.warnings.length?'存在待核查信息':'未发现结构错误'}</div>
    ${warnings(data.warnings)}
    <details class="accordion"><summary>分析限制（${data.limitations.length} 项）</summary><div class="accordion-body">${data.limitations.map(x=>`<p>${esc(x)}</p>`).join('')}</div></details>
    <details class="accordion"><summary>历史特征清单</summary><div class="accordion-body">${realHistoryTable(series)}</div></details>
    <p class="hint">直接使用客户提供的特征与频谱，不复算信号。</p>`;
}
function renderReal(data) {
  document.getElementById('report-audit')?.remove();
  if(data.analysis.report_plan?.version==='reader_report_v3')return renderReaderReport(data);
  const a=data.analysis,base=`/api/reports/${encodeURIComponent(data.id)}/files/`;
  const matching=data.decision.profile==='mechanism_matching_v2';
  const section=(n,title,body)=>`<section class="report-section"><h3><span>${n}</span>${title}</h3>${body}</section>`;
  const chart=ch=>`<figure class="source-figure"><figcaption>${esc(ch.title)} <span class="caption">${esc(ch.dataset_id)}</span></figcaption><img src="${base+encodeURIComponent(ch.file)}" alt="真实采集数据 ${esc(ch.title)}" loading="lazy"><p class="caption">来源 ${esc(ch.source)} · 单位 ${esc(ch.unit)} · 按原始坐标绘制</p></figure>`;
  const refs=[...new Set([...(data.text.citations || []),...(matching?data.decision.rules.map(r=>r.knowledge_id).filter(Boolean):[])])];
  const ev=Object.fromEntries(a.evidence_items.map(e=>[e.id,e]));
  const evidenceLink=id=>{const e=ev[id];return e?`<p class="caption"><span class="numeric">${esc(id)}</span> ${esc(e.name)}：<span class="numeric">${esc(e.y ?? e.amplitude)} ${esc(e.unit)}</span>；${esc(e.file)}，原始行 ${esc(e.source_row)}${e.x?'，'+esc(e.x):''}</p>`:'';};
  const hypotheses=(data.text.hypotheses || []).map(h=>`<div class="rule-row"><span class="tag tag-warning">待核查</span><strong>${esc(h.fault)}</strong><p>${esc(h.explanation)}</p><p class="caption">支持依据</p>${h.supporting_evidence.map(evidenceLink).join('')}${h.conflicting_evidence.length?'<p class="caption">矛盾或限制依据</p>'+h.conflicting_evidence.map(evidenceLink).join(''):''}<p>待补条件：${esc(h.missing_evidence.join('；') || '仍需现场验证')}</p><p class="citation">机理引用：${h.knowledge_ids.map(esc).join('、')}</p></div>`).join('');
  const orders=a.order_coordinates.length?`<div class="table-scroll"><table><thead><tr><th>阶次</th><th class="numeric">参考频率 Hz</th><th class="numeric">加速度幅值 m/s²</th><th>原始行号</th></tr></thead><tbody>${a.order_coordinates.map(x=>`<tr><td>${x.order}X</td><td class="numeric">${esc(x.hz)}</td><td class="numeric">${x.amplitude===null?'无精确坐标':esc(x.amplitude)}</td><td class="numeric">${esc(x.source_row || '—')}</td></tr>`).join('')}</tbody></table></div>`:'';
  const status=a.acquisition_status;
  const facts=`<div class="table-scroll"><table class="device-scope-table"><colgroup><col style="width:18%"><col style="width:24%"><col style="width:16%"><col style="width:42%"></colgroup><tbody>
    <tr><th scope="row">设备名称</th><td>${esc(data.device.name)}</td><th scope="row">安装区域</th><td>${esc(data.device.region_name || data.device.location || '未提供')}</td></tr>
    <tr><th scope="row">设备编码</th><td class="device-code">${esc(data.device.device_code || '未提供')}</td><th scope="row">监测部位</th><td>${esc(data.device.measure_point_name || '未提供')}</td></tr>
    <tr><th scope="row">采集工况</th><td colspan="3">${esc(status?.label || '未统计（历史报告未提供）')}</td></tr>
  </tbody></table></div>
  <p class="caption">速度有效值 &gt; 0.2 mm/s 为运行，≤ 0.2 mm/s 为停机；按记录数统计，非运行时长占比。${status?.available?`共 ${status.total} 条：运行 ${status.running_count} 条，停机 ${status.stopped_count} 条。`:''}</p>
  <details><summary>数据缺口与分析限制（${a.missing.length} 项）</summary><div class="accordion-body">${a.missing.map(v=>`<p>${esc(v)}</p>`).join('')}</div></details>`;
  const rules=data.decision.rules.map(r=>`<div class="rule-row"><span class="tag tag-warning">${esc(r.status)}</span><strong>${esc(r.name)}</strong><p>${esc(r.detail)}</p><p class="citation">${esc(r.source)}</p></div>`).join('');
  const correspondence=`<div class="table-scroll"><table><thead><tr><th>输入</th><th>报告位置</th><th>数据来源</th></tr></thead><tbody>${a.chart_manifest.map(ch=>`<tr><td>${esc(ch.dataset_id)} ${esc(ch.title)}</td><td>${ch.kind==='trend'?'03 振动趋势':ch.kind==='waveform'?'04 时域波形':'05 幅值频谱'}</td><td>${esc(ch.source)}</td></tr>`).join('')}</tbody></table></div>`;
  $('empty').hidden=true;$('report').hidden=false;$('report-state').textContent='真实数据报告';
  $('downloads').innerHTML=`${data.pdf.available?`<a class="button primary" href="${base}report.pdf" target="_blank" rel="noopener">查看 PDF</a>`:''}<a class="button" href="${base}report.docx">下载 Word</a><a class="text-link" href="${base}evidence.json" target="_blank" rel="noopener">依据</a><a class="text-link" href="${base}writer_input.json" target="_blank" rel="noopener">写作输入</a>`;
  $('report').innerHTML=`<header class="report-header"><h1>${esc(data.device.component+data.device.point_name)}状态分析报告</h1><div class="report-location">${esc(data.device.location)} / ${esc(data.device.name)}</div></header>
    <section class="conclusion"><h3><span>01</span>结论摘要</h3><strong>${esc(data.decision.state)}</strong><p>${esc(data.summary)}</p><p><strong>${data.writer.mode==='llm'?'模型分析':'固定说明'}：</strong>${esc(data.text.mechanism)}</p></section>${warnings(a.warnings)}
    ${section('02','设备与数据范围',facts)}
    ${section('03','振动趋势','<p class="caption">各项特征按实际采集时间展示，保留不同采集时段的分布。</p>'+a.chart_manifest.filter(ch=>ch.kind==='trend').map(chart).join(''))}
    ${section('04','时域波形',a.chart_manifest.filter(ch=>ch.kind==='waveform').map(chart).join('') || '<p>未提供波形。</p>')}
    ${section('05','幅值频谱',a.chart_manifest.filter(ch=>ch.kind==='spectrum').map(chart).join('')+orders+'<p class="caption">倍频表为精确坐标读取，不是峰值搜索；不插值，不推断全谱主峰。本版按用户约定，以频谱纵坐标和速度有效值的输入数值计算业务比值，不做单位转换；不作为无量纲物理能量比。</p>')}
    ${section('06','综合判定',matching?mechanismRuleRows(data.decision,base)+`<p>${esc(data.text.limitations)}</p>`:`<p>${esc(data.text.limitations)}</p>${hypotheses || '<p>本次未形成带完整证据引用的故障假设。</p>'}<details><summary>独立规则执行记录</summary>${rules}</details>`)}
    ${section('07','检维修措施',`<p><strong>现场复核：</strong>${esc(data.text.action1)}</p><p><strong>检修闭环：</strong>${esc(data.text.action2)}</p>`)}
    ${section('08','参考源与编制记录',`${matching?'<p class="caption">判定口径：各条件等权，满足率为满足条件数占总条件数的比例，不代表故障概率或严重程度。各历史时刻共用最新频谱作为参考，不代表当时实测频谱。运行状态、方向及负载不作为本次规则的前置条件。</p>':''}<p class="caption">确定性内容为台账、数值、坐标和独立规则结果；机理规则的条件数、支持等级和故障方向由程序生成；模型负责解释与建议，需人工复核。</p>${data.knowledge.filter(k=>refs.includes(k.id)).map(k=>`<p class="citation">[${esc(k.id)}] ${esc(k.source)} / ${esc(k.section)}</p>`).join('')}<p class="caption">${esc(data.writer.message)}</p><p class="caption">全部 ${data.knowledge.length} 条知识载入写作上下文；${matching?'程序已匹配全部记录，模型接收条件统计、最近和最高匹配记录及来源；逐次结果见明细CSV，不接收图像。':'模型接收每组历史首末值、记录数及来源，不接收全量历史曲线或图像。'}</p>${correspondence}<p class="caption">报告编号 ${esc(data.id)}${data.pdf.available?'':'；PDF未生成：'+esc(data.pdf.reason)}</p>`)} `;
}

function renderReaderReport(data) {
  const a=data.analysis,plan=a.report_plan,base=`/api/reports/${encodeURIComponent(data.id)}/files/`;
  let number=0;
  const section=(title,body)=>`<section class="report-section"><h3><span>${String(++number).padStart(2,'0')}</span>${title}</h3>${body}</section>`;
  const explanations=new Map(data.text.chart_explanations.map(x=>[x.dataset_id,x]));
  const chart=ch=>`<figure class="source-figure"><img src="${base+encodeURIComponent(ch.file)}" alt="${esc(ch.title)}" loading="lazy"><p><strong>机理含义：</strong>${esc(explanations.get(ch.dataset_id)?.text || '')}</p></figure>`;
  const scope=`<div class="table-scroll"><table class="device-scope-table"><colgroup><col style="width:18%"><col style="width:24%"><col style="width:16%"><col style="width:42%"></colgroup><tbody>
  <tr><th scope="row">设备名称</th><td>${esc(data.device.name)}</td><th scope="row">安装区域</th><td>${esc(data.device.region_name || data.device.location || '未提供')}</td></tr>
  <tr><th scope="row">设备编码</th><td class="device-code">${esc(data.device.device_code || '未提供')}</td><th scope="row">监测部位</th><td>${esc(data.device.measure_point_name || '未提供')}</td></tr>
  <tr><th scope="row">采集工况</th><td colspan="3">${esc(a.acquisition_status?.label || '未统计')}（记录占比）</td></tr></tbody></table></div>`;
  const start=data.decision.trend_start?.slice(0,10),end=data.decision.trend_end?.slice(0,10);
  let html=`<header class="report-header"><h1>${esc(data.device.name)}状态分析报告</h1><div class="report-location">${esc(data.device.region_name || data.device.location)}${start&&end?' | 数据时间区间 '+esc(start)+' 至 '+esc(end):''}</div></header>`;
  html+=section('结论摘要',`<p><strong>当前状态：</strong>${esc(plan.conclusion)}</p><p>${esc(data.text.mechanism)}</p>`);
  html+=section('设备与数据范围',scope);
  for(const [kind,title] of [['trend','振动趋势'],['waveform','时域波形'],['spectrum','幅值频谱']]) {
    const charts=a.chart_manifest.filter(ch=>ch.kind===kind);
    if(charts.length)html+=section(title,charts.map(chart).join(''));
  }
  html+=section('综合判定',`<p><strong>当前判定：</strong>${esc(data.text.assessment)}</p>`);
  html+=section('检维修措施',`<p><strong>现场复核：</strong>${esc(data.text.action1)}</p><p><strong>检修闭环：</strong>${esc(data.text.action2)}</p>`);
  const references=new Map();
  for(const k of data.knowledge.filter(k=>data.text.citations.includes(k.id))){
    if(!references.has(k.source))references.set(k.source,[]);
    references.get(k.source).push(`[${k.id}] ${k.section}`);
  }
  html+=section('参考源',[...references].map(([source,entries])=>`<p class="citation">来源文件：${esc(source)}</p><p class="citation">引用条目：${esc(entries.join('；'))}</p>`).join('') || '<p>本次未引用具体机理条目。</p>');
  $('empty').hidden=true;$('report').hidden=false;$('report-state').textContent='真实数据报告';$('report').innerHTML=html;
  $('downloads').innerHTML=`${data.pdf.available?`<a class="button primary" href="${base}report.pdf" target="_blank" rel="noopener">查看 PDF</a>`:''}<a class="button" href="${base}report.docx">下载 Word</a><a class="text-link" href="${base}evidence.json" target="_blank" rel="noopener">依据</a><a class="text-link" href="${base}writer_input.json" target="_blank" rel="noopener">写作输入</a>`;
  const audit=document.createElement('section');audit.id='report-audit';audit.className='report-section';
  audit.innerHTML=`<details class="accordion"><summary>核查资料（不纳入导出报告）</summary><div class="accordion-body"><p>${esc(data.writer.message)}</p><p>${esc(plan.selection_policy)}</p><p>${esc(plan.line_policy)}</p><p>${esc(data.text.limitations)}</p>${warnings(a.warnings)}${mechanismRuleRows(data.decision,base)}</div></details>`;
  $('report').after(audit);
}
