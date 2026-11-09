const $ = id => document.getElementById(id);
const esc = s => String(s ?? '未提供').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const nf = (v, n = 3) => v == null ? '未提供' : Number(v).toFixed(n);
const labels = {
  velocity_rms:['速度有效值','mm/s'], acceleration_rms:['加速度有效值','m/s²'],
  acceleration_peak:['加速度峰值','m/s²'], kurtosis:['峭度','无量纲'],
  skewness:['偏度','无量纲'], crest_factor:['峰值因子','无量纲']
};
let active = null, caseId = null, busy = false, contextLimit = 0;

async function request(url, opts) {
  let response;
  try { response = await fetch(url, opts); }
  catch { throw Error('连接中断，请检查服务器连接与端口转发后刷新页面。'); }
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
const post = (url, data, method = 'POST') => request(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
function syncButton() { $('generate').disabled = !caseId || busy; $('import-case').disabled = busy; }
function warnings(items) { return (items || []).map(x => `<div class="warning">${esc(x)}</div>`).join(''); }
function highlightNumbers(text) {
  const source = String(text ?? '未提供');
  let result = '', cursor = 0;
  for (const match of source.matchAll(/-?\d+(?:\.\d+)?(?:\s*(?:mm\/s|m\/s²|Hz|r\/min|%))?/g)) {
    result += esc(source.slice(cursor, match.index)) + `<span class="number-chip">${esc(match[0])}</span>`;
    cursor = match.index + match[0].length;
  }
  return result + esc(source.slice(cursor));
}
function featureTable(uploaded, computed) {
  return `<div class="table-scroll"><table class="feature-table"><thead><tr><th>当前特征</th><th>单位</th><th class="numeric">上传值</th><th class="numeric">波形复算值</th></tr></thead><tbody>${Object.entries(labels).map(([key,[label,unit]]) => `<tr><td>${label}</td><td class="unit">${unit}</td><td class="numeric">${nf(uploaded?.[key])}</td><td class="numeric">${nf(computed?.[key])}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderCasePreview(data, archived = false) {
  if (data.mode === 'real_measurement') return realCasePreview(data, archived);
  const panel = $('case-preview');
  const uploaded = data.has_waveform ? Object.fromEntries(data.comparisons.map(r => [r.feature, r.uploaded])) : data.features;
  const computed = Object.fromEntries(data.comparisons.map(r => [r.feature, r.recomputed]));
  panel.hidden = false;
  panel.innerHTML = `<h2>数据检查信息</h2><span class="case-title">${esc(data.title)}${archived ? ' · 报告关联案例' : ''}</span>
    <dl class="case-meta">
      <dt>设备</dt><dd>${esc(data.device.name)} / ${esc(data.device.model)}</dd>
      <dt>测点</dt><dd>${esc(data.device.point_name)}</dd>
      <dt>采集时间</dt><dd class="data-value">${esc(data.measurement.measured_time.replace('T',' '))}</dd>
      <dt>采样频率</dt><dd class="data-value">${nf(data.measurement.sampling_rate,0)} Hz</dd>
      <dt>采样点数</dt><dd class="data-value">${nf(data.measurement.sample_count,0)} 点</dd>
      <dt>采样时长</dt><dd class="data-value">${nf(data.measurement.duration_seconds,2)} s</dd>
      <dt>历史记录</dt><dd><span class="numeric">${data.history_count}</span> 条</dd>
      <dt>原始波形</dt><dd>${data.has_waveform ? '<span class="tag tag-success">已提供</span>' : '<span class="tag tag-warning">未提供</span>'}</dd>
      <dt>转速</dt><dd>${data.device.rpm ? `<span class="numeric">${esc(data.device.rpm)} r/min</span>` : '<span class="tag tag-warning">未提供</span>'}</dd>
    </dl>
    <div class="case-check ${data.warnings.length ? 'has-warning' : ''}">${data.warnings.length ? '发现差异，须核查' : '已通过输入检查'} · 模拟数据</div>
    ${warnings(data.warnings)}
    ${data.limitations.length ? `<details class="accordion"><summary>${data.limitations.length === 1 ? esc(data.limitations[0]) : `分析限制（${data.limitations.length} 项）`}</summary><div class="accordion-body">${data.limitations.map(x => `<p>${esc(x)}</p>`).join('')}</div></details>` : ''}
    <details class="accordion"><summary>${data.has_waveform ? '当前特征核对' : '上传当前特征'}</summary><div class="accordion-body">${featureTable(uploaded, computed)}</div></details>
    ${archived ? '<p class="hint">重新生成报告时，请先上传案例数据包。</p>' : ''}`;
}

async function init() {
  try {
    const config = await request('/api/config');
    contextLimit = config.context_limit;
    $('llm').checked = false;
    $('model-note').textContent = config.model_enabled ? (config.model_local ? `本地模型 ${config.model_name}。勾选后由学校服务器内的模型撰写说明与建议；默认使用固定说明。` : `可选模型 ${config.model_name}（${config.model_host}）。勾选后将向此接口发送整理后的实测依据与知识条目；默认使用固定说明。`) : '未配置模型，将使用固定文字模板。';
    $('rules').value = JSON.stringify(await request('/api/rules'), null, 2);
    await updateKnowledge();
    const id = new URLSearchParams(location.search).get('report');
    if (id) { active = id; await poll(); }
  } catch (error) { $('status').textContent = error.message; }
}

$('case-file').onchange = () => {
  caseId = null; syncButton(); $('case-preview').hidden = true;
  const file = $('case-file').files[0];
  $('case-filename').textContent = file?.name || 'ZIP 文件，最大 20 MB';
  document.querySelector('.file-select').classList.toggle('has-file', !!file);
  $('status').textContent = '点击“导入并检查”，确认案例数据。';
};
$('import-case').onclick = async () => {
  try {
    const file = $('case-file').files[0];
    if (!file) throw Error('请先选择 ZIP 案例数据包。');
    if (file.size > 20 * 1024 * 1024) throw Error('案例 ZIP 不能超过 20 MB。');
    $('import-case').disabled = true;
    $('status').textContent = '正在解析与检查案例…';
    const form = new FormData(); form.append('file', file);
    const data = await request('/api/cases', {method:'POST', body:form});
    caseId = data.case_id; renderCasePreview(data);
    $('status').textContent = '案例已导入，可生成报告。';
  } catch (error) { caseId = null; $('case-preview').hidden = true; $('status').textContent = error.message; }
  finally { syncButton(); }
};
$('generate').onclick = async () => {
  try {
    busy = true; syncButton(); $('steps').innerHTML = '';
    $('status').textContent = '正在创建报告…';
    const result = await post('/api/reports', {case_id:caseId, use_llm:$('llm').checked});
    active = result.id; history.replaceState(null, '', '?report=' + active);
    await poll();
  } catch (error) { $('status').textContent = error.message; busy = false; syncButton(); }
};
async function poll() {
  try {
    const data = await request('/api/reports/' + active);
    $('steps').innerHTML = (data.events || []).map(e => `<li>${e.node ? `<span class="numeric">${esc(e.node)}</span><br>` : ''}${esc(e.step)}</li>`).join('');
    if (data.status === 'running') {
      busy = true; syncButton(); $('status').textContent = '正在生成报告…'; setTimeout(poll, 1200); return;
    }
    busy = false; syncButton();
    if (data.status === 'failed') throw Error(data.error);
    $('status').textContent = data.writer?.mode === 'llm'
      ? `报告已生成，正文使用 ${data.writer.model || '大模型'} 撰写，请复核后使用。`
      : `报告已生成，正文使用固定说明。${data.writer?.message || '未采用大模型正文。'}`;
    render(data);
    if (!caseId && !$('case-file').files.length) await restoreCasePreview(data);
  } catch (error) { $('status').textContent = error.message; busy = false; syncButton(); }
}
async function restoreCasePreview(report) {
  try {
    const snapshot = await request(`/api/reports/${encodeURIComponent(report.id)}/files/snapshot.json`);
    if (caseId || $('case-file').files.length || active !== report.id) return;
    renderCasePreview({title:report.case_title || snapshot.title, device:report.device, mode:report.mode,
      is_test_data:report.is_test_data || snapshot.is_test_data,data_notice:report.data_notice || snapshot.data_notice,
      data_origin:report.data_origin || snapshot.data_origin || snapshot.case_manifest?.data_type,
      measurement:snapshot, history_count:snapshot.history.length, has_waveform:snapshot.waveform != null,
      warnings:report.analysis.warnings, limitations:report.analysis.missing,
      comparisons:report.analysis.comparisons || [], features:report.analysis.uploaded_features || report.analysis.features,
      series:report.analysis.series || [],chart_manifest:report.analysis.chart_manifest || [],
      acquisition_status:report.analysis.acquisition_status,
      order_coordinates:report.analysis.order_coordinates || [],has_spectrum:report.analysis.spectrum_provided}, true);
  } catch { /* The report remains available when an older archive lacks a snapshot. */ }
}

function render(data) {
  if (data.mode === 'real_measurement') return renderReal(data);
  const base = `/api/reports/${encodeURIComponent(data.id)}/files/`;
  const analysis = data.analysis;
  const section = (number, title, body) => `<section class="report-section"><h3><span>${number}</span>${title}</h3>${body}</section>`;
  const image = (file, alt) => `<img src="${base + file}.png" alt="${esc(alt)}" loading="lazy">`;
  $('empty').hidden = true; $('report').hidden = false;
  $('report-state').textContent = data.case_title || '已生成';
  $('downloads').innerHTML = `${data.pdf.available ? `<a class="button primary" href="${base}report.pdf" target="_blank" rel="noopener">查看 PDF</a>` : ''}<a class="button" href="${base}report.docx">下载 Word</a><a class="text-link" href="${base}evidence.json" target="_blank" rel="noopener">依据</a><a class="text-link" href="${base}writer_input.json" target="_blank" rel="noopener">写作输入</a>`;

  const facts = `<div class="table-scroll"><table class="facts"><tbody>
    <tr><th scope="row">设备 / 型号</th><td>${esc(data.device.name)} / ${esc(data.device.model)}</td><th scope="row">测点方向</th><td>${esc(data.device.direction)}</td></tr>
    <tr><th scope="row">转速</th><td class="numeric">${data.device.rpm ? esc(data.device.rpm) + ' r/min' : '未提供'}</td><th scope="row">工况</th><td>${esc(data.device.load)}</td></tr>
    <tr><th scope="row">数据模式</th><td><span class="tag">模拟数据</span></td><th scope="row">严重程度</th><td><span class="tag tag-warning">未分级</span></td></tr>
    </tbody></table></div><p class="feature-source">特征来源：${esc(analysis.feature_source || '历史版本程序计算')}，复算对比容差：相对误差 1% 或绝对误差 0.001。</p>
    ${featureTable(analysis.uploaded_features || analysis.features, analysis.recomputed_features || {})}
    <p class="caption">数据缺口与分析限制：${esc(analysis.missing.join('；') || '未发现已检查项目的数据缺失')}</p>`;
  const trend = `${image('trend','模拟速度有效值趋势')}<p>历史有效区间起始 <span class="numeric">${nf(data.decision.first)} mm/s</span>，末值 <span class="numeric">${nf(data.decision.last)} mm/s</span>，变化 <span class="numeric">${nf(data.decision.change_percent,1)}%</span>。</p><p class="caption">${esc(data.decision.rules.find(r => r.kind === 'demo_trend')?.detail || '详见独立规则结果')}。演示阈值不代表行业标准。</p>`;
  const spectrum = `${image('spectrum','模拟加速度幅值频谱')}<p>${analysis.peaks.length ? '主要频率峰：' + analysis.peaks.map(p => `<span class="numeric">${nf(p.hz,1)} Hz / ${nf(p.amplitude)} m/s²</span>`).join('；') + '。' : '未提供当前波形，不生成频谱或推测频率峰。'}</p><p class="caption">${analysis.rpm_available ? '频率峰的机理解释须结合可信转速与同工况证据。' : '缺少可信转速，不将频率峰标记为转频阶次。'}</p>`;
  const rules = `<p>${esc(data.decision.state)}。${esc(data.text.limitations)}</p>${data.decision.rules.map(rule => `<div class="rule-row"><span class="tag ${/未知|待|不执行/.test(rule.status) ? 'tag-warning' : ''}">${esc(rule.status)}</span><strong>${esc(rule.name)}</strong><p>${esc(rule.detail)}</p>${(rule.conditions || []).map(c => `<div class="rule-conditions">${esc(c.name)}：<span class="numeric">${nf(c.value)}</span> · ${esc(c.status)}</div>`).join('')}<div class="citation">${esc(rule.source)}</div></div>`).join('')}`;
  const references = `${data.text.citations.length ? data.knowledge.filter(k => data.text.citations.includes(k.id)).map(k => `<p class="citation"><span class="numeric">[${esc(k.id)}]</span> ${esc(k.source)} · ${esc(k.section)}</p>`).join('') : '<p class="citation">本次文字未引用特定知识条目。</p>'}
    <p class="caption">${esc(data.writer.message)}。</p>${data.writer.context ? `<p class="caption">写作资料：全部 <span class="numeric">${data.writer.context.knowledge_count}</span> 条知识；输入保守上界 <span class="numeric">${data.writer.context.input_token_upper_bound}</span> tokens，配置窗口 <span class="numeric">${data.writer.context.context_limit}</span> tokens。未截断知识。</p>` : ''}
    <p class="caption">报告编号 <span class="numeric">${esc(data.id)}</span>。${!data.pdf.available ? 'PDF 未生成：' + esc(data.pdf.reason) : ''}</p><details><summary>信号处理口径</summary><div class="accordion-body">${Object.entries(data.processing).map(([key,value]) => `<p class="caption">${esc(key)}：${esc(value)}</p>`).join('')}</div></details>`;

  $('report').innerHTML = `<header class="report-header"><span class="stamp">模拟数据 · 仅用于功能演示</span><h1>${esc(data.device.name + data.device.component)}状态分析报告</h1><div class="report-location">${esc(data.device.location)} / ${esc(data.device.point_name)}</div><div class="meta">采集时间 <span class="numeric">${esc(data.measured_time.replace('T',' '))}</span> · 案例 ${esc(data.case_title || data.case_id || '历史报告')}</div></header>
    <section class="conclusion"><h3><span>01</span>结论摘要</h3><strong class="important-warning">${esc(data.decision.state)}</strong><p>${highlightNumbers(data.summary)}</p></section>${warnings(analysis.warnings)}
    ${section('02','设备与数据范围',facts)}
    ${section('03','振动趋势',trend)}
    ${section('04','时域波形',image('waveform','模拟加速度时域波形') + `<p>${esc(data.text.mechanism)}</p>`)}
    ${section('05','幅值频谱',spectrum)}
    ${section('06','综合判定',rules)}
    ${section('07','检维修措施',`<p><strong>现场复核：</strong>${esc(data.text.action1)}</p><p><strong>检修闭环：</strong>${esc(data.text.action2)}</p>`)}
    ${section('08','参考源与编制记录',references)}`;
}

async function updateKnowledge() {
  const knowledge = await request('/api/knowledge');
  $('knowledge-total').textContent = knowledge.length + ' 条';
  const bytes = new TextEncoder().encode(JSON.stringify(knowledge)).length;
  $('knowledge-budget').textContent = `已导入全部 ${knowledge.length} 条，知识 JSON 约 ${bytes.toLocaleString()} 字节。写作前按完整输入检查上下文；配置窗口 ${contextLimit.toLocaleString()} tokens，超限时停止并提示。`;
  $('knowledge-list').innerHTML = knowledge.map(item => `<details class="knowledge-entry"><summary><span>${esc(item.id)}</span>${esc(item.category)} / ${esc(item.fault)}</summary><div class="accordion-body">${[['phenomena','机理现象'],['causes','原因'],['actions','措施'],['rule_text','规则原文（执行配置见诊断规则入口）']].map(([key,label]) => `<h4>${label}</h4><p>${esc(item[key] || '文档未提供')}</p>`).join('')}<p class="citation">来源：${esc(item.source)} · ${esc(item.section)}</p></div></details>`).join('') || '<p class="hint">尚未导入知识文档。请使用一级标题划分设备类别、二级标题划分故障名称。</p>';
}
for (const name of ['knowledge','rules']) {
  const dialog = $(`${name}-dialog`), button = $('open-' + name);
  button.onclick = () => { button.setAttribute('aria-expanded','true'); dialog.showModal(); };
  dialog.addEventListener('close', () => button.setAttribute('aria-expanded','false'));
}
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close());
$('upload').onclick = async () => {
  try {
    const file = $('knowledge-file').files[0]; if (!file) throw Error('请先选择 DOCX 知识文档。');
    $('upload').disabled = true;
    const form = new FormData(); form.append('file',file);
    const result = await request('/api/knowledge',{method:'POST',body:form});
    await updateKnowledge(); $('knowledge-status').textContent = `已导入 ${result.count} 条。${result.message}`;
  } catch (error) { $('knowledge-status').textContent = error.message; }
  finally { $('upload').disabled = false; }
};
$('save-rules').onclick = async () => {
  try { await post('/api/rules',JSON.parse($('rules').value),'PUT'); $('rules-status').textContent = '规则已保存，新报告将使用此配置。'; }
  catch (error) { $('rules-status').textContent = error.message; }
};
init();
