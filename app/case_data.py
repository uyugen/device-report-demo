"""Bounded ZIP ingestion. Never extract uploaded members onto the filesystem."""
import csv
import io
import json
import math
from datetime import datetime
from zipfile import ZipFile, BadZipFile
import numpy as np

MAX_ZIP = 20 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024
FEATURES = ['velocity_rms', 'acceleration_rms', 'acceleration_peak', 'kurtosis', 'skewness', 'crest_factor']
UNITS = {'velocity_rms': 'mm/s', 'acceleration_rms': 'm/s²', 'acceleration_peak': 'm/s²',
         'kurtosis': '1', 'skewness': '1', 'crest_factor': '1'}
META = ['case_id', 'point_id', 'measured_time']
PROCESSING = {'velocity': 'FFT积分，剔除10 Hz以下成分，输出mm/s',
              'kurtosis': '中心四阶矩/方差平方，非超额峭度', 'peak': '绝对峰值',
              'spectrum': 'Hann窗，单边峰值幅度，相干增益修正'}


def number(value, label, nullable=False):
    if nullable and (value is None or value == ''):
        return None
    if isinstance(value, bool):
        raise ValueError(f'{label} 必须是有限数值')
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} 必须是有限数值') from None
    if not math.isfinite(n):
        raise ValueError(f'{label} 不能是 NaN 或无穷值')
    return n


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError('measured_time 必须是 ISO 8601 时间') from None


def csv_rows(raw, name, required, max_rows):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'{name} 缺少表头或含重复表头')
        if not set(required).issubset(reader.fieldnames):
            raise ValueError(f'{name} 缺少列：{", ".join(set(required)-set(reader.fieldnames))}')
        rows = []
        for row in reader:
            if len(rows) >= max_rows or None in row or any(v is None for v in row.values()):
                raise ValueError(f'{name} 行数超限或列数不一致')
            rows.append(row)
        if not rows:
            raise ValueError(f'{name} 不能为空')
        return rows
    except UnicodeDecodeError:
        raise ValueError(f'{name} 请使用 UTF-8 编码') from None


def parse_zip(raw):
    if len(raw) > MAX_ZIP:
        raise ValueError('案例ZIP不能超过20MB')
    allowed = {'case.json', 'history.csv', 'current_features.csv', 'waveform.csv'}
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or set(names)-allowed:
                raise ValueError('ZIP只允许根目录四个约定文件，不接受子目录、重复文件或其他文件')
            if not {'case.json', 'history.csv', 'current_features.csv'}.issubset(names):
                raise ValueError('ZIP必须包含case.json、history.csv和current_features.csv')
            if sum(i.file_size for i in infos) > MAX_EXPANDED or any(i.flag_bits & 1 for i in infos):
                raise ValueError('ZIP解压总量不能超过40MB，不接受加密文件')
            data = {i.filename: z.read(i) for i in infos}
    except (BadZipFile, RuntimeError, NotImplementedError):
        raise ValueError('ZIP文件损坏或压缩格式不支持') from None
    try:
        case = json.loads(data['case.json'].decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('case.json 不是有效UTF-8 JSON') from None
    if not isinstance(case, dict):
        raise ValueError('case.json 必须是对象')
    history = csv_rows(data['history.csv'], 'history.csv', META+FEATURES, 10000)
    current = csv_rows(data['current_features.csv'], 'current_features.csv', META+FEATURES, 1)[0]
    for row in history+[current]:
        for key in FEATURES:
            row[key] = number(row[key], key, nullable=True)
    wave = None
    times = None
    if 'waveform.csv' in data:
        rows = csv_rows(data['waveform.csv'], 'waveform.csv', ['time_seconds', 'acceleration'], 200000)
        times = [number(r['time_seconds'], 'time_seconds') for r in rows]
        wave = [number(r['acceleration'], 'acceleration') for r in rows]
    return {**case, 'mode': 'simulated', 'history': history, 'current_features': current,
            'waveform': wave, 'waveform_times': times, 'processing': PROCESSING.copy()}


def check_snapshot(s):
    """Fatal schema/units errors stop; missing evidence and mismatches remain visible."""
    if s.get('schema_version') != 1 or s.get('simulated') is not True:
        raise ValueError('仅接受schema_version=1且simulated=true的模拟案例')
    for key in ['case_id', 'title', 'measured_time']:
        if not isinstance(s.get(key), str) or not s[key].strip() or len(s[key]) > 200:
            raise ValueError(f'case.json 缺少或无效字段：{key}')
    d = s.get('device')
    if not isinstance(d, dict):
        raise ValueError('case.json 缺少device对象')
    for key in ['id', 'name', 'type', 'model', 'point_id', 'point_name', 'direction', 'component', 'location', 'load']:
        if not isinstance(d.get(key), str) or not d[key].strip() or len(d[key]) > 300:
            raise ValueError(f'设备台账缺少或无效字段：device.{key}')
    if 'rpm' not in d:
        raise ValueError('请提供device.rpm；未知转速使用null')
    rpm = number(d['rpm'], 'device.rpm', nullable=True)
    if rpm is not None and rpm < 0:
        raise ValueError('转速不能为负数')
    d['rpm'] = rpm if rpm else None
    fs = number(s.get('sampling_rate'), 'sampling_rate')
    n = number(s.get('sample_count'), 'sample_count')
    duration = number(s.get('duration_seconds'), 'duration_seconds')
    if not 20 <= fs <= 1000000 or not n.is_integer() or not 32 <= n <= 200000 or duration <= 0:
        raise ValueError('采样频率须为20～1000000Hz，点数须为32～200000的整数，时长须大于零')
    s['sampling_rate'], s['sample_count'], s['duration_seconds'] = fs, int(n), duration
    if not math.isclose(n/fs, duration, rel_tol=1e-6, abs_tol=1e-9):
        raise ValueError('采样点数÷采样频率与采样时长不一致')
    if s.get('unit') != 'm/s²' or s.get('feature_units') != UNITS:
        raise ValueError('单位不符合约定：波形m/s²、速度mm/s、加速度m/s²、无量纲指标1；暂不隐式换算')
    target = timestamp(s['measured_time'])
    warnings, limitations = [], []
    if not d['rpm']:
        limitations.append('缺少可信转速，不作转频阶次判断'+('；波形可用时保留绝对频率分析' if s['waveform'] is not None else ''))
    for row in s['history']+[s['current_features']]:
        if row['case_id'] != s['case_id'] or row['point_id'] != d['point_id']:
            raise ValueError('CSV的case_id或point_id与case.json不对应')
        timestamp(row['measured_time'])
        for key in FEATURES:
            value = row[key]
            if value is not None and key != 'skewness' and value < 0:
                raise ValueError(f'{key} 不能为负数')
    times = [timestamp(r['measured_time']) for r in s['history']]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError('历史时间必须严格递增且不能重复')
    if times[-1] != target or timestamp(s['current_features']['measured_time']) != target:
        raise ValueError('历史末行和当前特征的时间必须与case.json采集时间一致')
    for key in FEATURES:
        a, b = s['history'][-1][key], s['current_features'][key]
        if (a is None) != (b is None) or (a is not None and not math.isclose(a,b,rel_tol=.01,abs_tol=.001)):
            warnings.append(f'历史末行与当前特征表不一致：{key}，请核查；趋势暂按历史表展示')
    if s['waveform'] is None:
        limitations.append('未提供原始波形：保留上传特征与历史趋势，无法复算特征或生成当前波形及频谱')
    else:
        if len(s['waveform']) != s['sample_count']:
            raise ValueError('waveform.csv点数与sample_count不一致')
        t = np.asarray(s['waveform_times'])
        if not np.allclose(t, np.arange(len(t))/fs, atol=max(1e-10,1/fs*1e-5), rtol=0):
            raise ValueError('波形时间列必须从零开始，且步长与采样频率一致')
    missing = [k for k in FEATURES if s['current_features'][k] is None]
    if missing:
        limitations.append('当前特征表缺少：'+', '.join(missing))
    if any(r['velocity_rms'] is None for r in s['history']):
        limitations.append('历史速度特征有缺失，图中留空；趋势规则仅使用有效区间端点')
    return {'warnings': warnings, 'limitations': limitations, 'status': '需核查' if warnings else '通过',
            'feature_tolerance': '相对误差1%或绝对误差0.001（按指标单位），超限提示核查'}
