"""Build portable v1.2 examples using no customer input or private knowledge file."""
from pathlib import Path
from datetime import datetime, timedelta
import csv
import hashlib
import io
import json
import zipfile

import numpy as np
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'examples'
UNITS = {'velocity_rms': 'mm/s', 'acceleration_rms': 'm/s²',
         'acceleration_peak': 'm/s²', 'kurtosis': '1', 'skewness': '1',
         'low_frequency_impulse': 'm/s²', 'vibration_impulse': 'g'}


def wave(fault):
    """Create one waveform whose four supplied statistics agree with its samples."""
    values = np.random.default_rng(20261106).normal(size=4096)
    values -= values.mean()
    if fault:
        for peak in np.arange(6.0, 12.0, 0.05):
            candidate = values.copy()
            candidate[900] = peak
            centered = candidate - candidate.mean()
            rms = float(np.sqrt(np.mean(candidate**2)))
            kurtosis = float(np.mean(centered**4) / np.mean(centered**2)**2)
            if 3.8 <= kurtosis < 4.2 and np.max(np.abs(candidate)) / rms >= 4.5:
                values = candidate
                break
        else:
            raise ValueError('Cannot construct the bearing example')
    values = np.round(values * (1.8 if fault else 1.2), 9)
    centered = values - values.mean()
    stats = {'acceleration_rms': float(np.sqrt(np.mean(values**2))),
             'acceleration_peak': float(np.max(np.abs(values))),
             'kurtosis': float(np.mean(centered**4) / np.mean(centered**2)**2),
             'skewness': float(np.mean(centered**3) / np.mean(centered**2)**1.5)}
    return values, stats


def csv_bytes(xs, ys):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['source_row', 'x', 'y'])
    for number, (x, y) in enumerate(zip(xs, ys), 2):
        writer.writerow([number, x, format(float(y), '.9f').rstrip('0').rstrip('.')])
    return stream.getvalue().encode('utf-8')


def save_zip(path, files):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 6, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def make_case(name, flags):
    times = [(datetime(2026, 11, 1, 8) + timedelta(minutes=10*i)).isoformat()
             for i in range(len(flags))]
    normal_wave, normal = wave(False)
    fault_wave, fault = wave(True)
    states = [fault if flag else normal for flag in flags]
    c = {'schema_version': '1.2', 'case_id': 'DEPLOY-' + name.upper(),
         'case_name': '部署验收电机状态分析',
         'device': {'device_id': 'DEMO-MOTOR-01', 'device_code': 'DEMO-001',
                    'device_name': '部署验收电机', 'device_type': '电动机',
                    'model': 'DEMO-MOTOR', 'region_name': '部署验收台'},
         'point': {'point_id': 'POINT-01', 'measure_point_name': '电机自由端',
                   'diagnostic_category': '电动机'},
         'rpm': 3000, 'latest_acquisition': {'measured_time': times[-1]},
         'spectrum_scope': 'shared_latest', 'datasets': []}
    values = {code: [s[code] for s in states] for code in normal}
    values['velocity_rms'] = [2.0 + 0.005*i if flag else 1.2 + 0.002*(i % 4)
                              for i, flag in enumerate(flags)]
    values['low_frequency_impulse'] = [10 + 0.02*(i % 4) if flag else 4 + 0.01*(i % 4)
                                     for i, flag in enumerate(flags)]
    values['vibration_impulse'] = [1.0 if flag else 0.3 for flag in flags]
    files = {}
    for code, unit in UNITS.items():
        path = 'data/' + code + '.csv'
        files[path] = csv_bytes(times, values[code])
        c['datasets'].append({'dataset_id': code.upper(), 'kind': 'trend',
                              'feature_code': code, 'data_file': path, 'unit': unit})
    current_wave = fault_wave if flags[-1] else normal_wave
    files['data/waveform.csv'] = csv_bytes(np.arange(len(current_wave))/2048, current_wave)
    c['datasets'].append({'dataset_id': 'WAVEFORM', 'kind': 'waveform',
                          'data_file': 'data/waveform.csv', 'unit': 'm/s²',
                          'sampling': {'sampling_rate_hz': 2048, 'sample_count': 4096,
                                       'duration_seconds': 2}})
    # Independently supplied reference spectrum, not an FFT of the latest waveform.
    # Exact 1X to 9X coordinates are present; all non-bearing rules also fail
    # their velocity condition, so no additional fault is introduced.
    frequencies = np.arange(0, 501, dtype=float)
    amplitudes = np.full(len(frequencies), 0.01)
    for order in range(1, 10):
        amplitudes[50*order] = 0.08 if order == 1 else 0.03
    files['data/spectrum.csv'] = csv_bytes(frequencies, amplitudes)
    c['datasets'].append({'dataset_id': 'SPECTRUM', 'kind': 'spectrum',
                          'data_file': 'data/spectrum.csv', 'unit': 'm/s²'})
    scores = [76 - 0.1*(i % 4) if flag else 96 - 0.1*(i % 4)
              for i, flag in enumerate(flags)]
    files['data/health_score.csv'] = csv_bytes(times, scores)
    c['datasets'].append({'dataset_id': 'HEALTH', 'kind': 'health_score',
                          'data_file': 'data/health_score.csv', 'unit': '分',
                          'health_model': {'model_name': '部署验收评分', 'model_version': '1.0',
                                           'algorithm_name': '接口评分展示',
                                           'calculation_status': 'OK',
                                           'configuration_name': '部署验收配置'}})
    files['case.json'] = json.dumps(c, ensure_ascii=False, indent=2).encode('utf-8')
    path = OUT / (name + '.zip')
    save_zip(path, files)
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'expected_status': '故障' if flags[-1] else '正常',
            'expected_faults': ['电机滚动轴承故障'] if flags[-1] else [],
            'history_normal': flags.count(False), 'history_fault': flags.count(True),
            'health_chart_required': True}


def make_knowledge(rules):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(2)
    sec.left_margin = sec.right_margin = Cm(2.2)
    for name, size in [('Normal', 10.5), ('Title', 19), ('Heading 1', 14), ('Heading 2', 12)]:
        style = doc.styles[name]
        style.font.name = 'Noto Sans CJK SC'
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), 'Noto Sans CJK SC')
        style.paragraph_format.space_after = Pt(5)
    doc.styles['Normal'].paragraph_format.line_spacing = 1.25
    # The bundled Word base document may carry a blue Title paragraph border.
    for border in list(doc.styles.element.xpath('.//w:pBdr')):
        border.getparent().remove(border)
    doc.add_paragraph('设备机理知识部署验收文档', style='Title')
    for border in list(doc.element.xpath('.//w:pBdr')):
        border.getparent().remove(border)
    doc.add_paragraph('供设备状态报告 Demo 的安装与流程验收使用。条目类别、故障名称和机理规则逐字对应仓库 config/rules.json；现象、原因和措施为简要说明，不替代企业正式知识文档或行业标准。')
    doc.add_heading('电动机', level=1)
    notes = {
        'MOTOR-001': ('关注峭度、低频冲击值及加速度峰值与有效值的比值，结合相同时间的三个条件判断。',
                      '滚动接触部件的局部损伤、润滑或装配问题可能引起冲击，需要现场核查具体原因。',
                      '先复核对应记录与测点安装，再检查润滑和轴承状态，依据检查结果安排维护。'),
        'MOTOR-002': ('关注一倍频幅值与速度有效值的比值、偶数倍频幅值之和及峭度和速度区间。',
                      '转子质量分布不均可能导致与转频相关的振动，不能仅凭单项幅值认定原因。',
                      '先核查传感器与安装紧固状态，再结合现场检查确认是否需要开展平衡检查。'),
        'MOTOR-003': ('关注二倍频幅值占比、三六九倍频幅值之和及峭度和速度区间。',
                      '轴系安装偏差或联接部位问题可能影响振动，需要现场确认对中与联接状态。',
                      '复核测量记录后检查轴系对中及联接状态，根据检查结果安排调整。'),
        'MOTOR-004': ('关注三六九倍频幅值之和与速度有效值的比值，以及速度有效值区间。',
                      '连接或基础紧固问题可能影响振动，规则匹配本身不能定位具体松动部位。',
                      '核查安装基础与连接紧固状态，保留检查结果并持续监测。'),
    }
    for index, rule in enumerate(rules):
        if index == 2:
            doc.add_page_break()
        doc.add_heading(rule['fault'], level=2)
        phenomenon, cause, action = notes[rule['id']]
        for label, value in [('机理现象', phenomenon), ('机理原因', cause),
                             ('解决措施', action), ('机理规则', rule['source_rule_text'])]:
            doc.add_paragraph(label + '：' + value)
    footer = sec.footer.paragraphs[0]
    footer.add_run('部署验收资料  ')
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    path = OUT / 'deployment_knowledge.docx'
    doc.save(path)
    return path


def main():
    OUT.mkdir(exist_ok=True)
    rules = json.loads((ROOT / 'config/rules.json').read_text(encoding='utf-8'))
    assert [r['id'] for r in rules] == ['MOTOR-001', 'MOTOR-002', 'MOTOR-003', 'MOTOR-004']
    knowledge = make_knowledge(rules)
    cases = [make_case('normal', [False]*24),
             make_case('bearing_fault', [False]*16 + [True]*8),
             make_case('historical_fault', [False]*8 + [True]*8 + [False]*8)]
    manifest = {'purpose': '独立部署验收资料，不使用客户原始数据；不代表真实设备故障。',
                'schema_version': '1.2',
                'knowledge': {'file': knowledge.name, 'count': 4,
                              'sha256': hashlib.sha256(knowledge.read_bytes()).hexdigest()},
                'cases': cases}
    (OUT / 'manifest.json').write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
