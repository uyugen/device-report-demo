"""Read customer final values. No feature extraction, FFT, integration or peak search."""
import csv
import hashlib
import io
import json
import math
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

MAX_ZIP = 20 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024
UNITS = {'velocity_rms': 'mm/s', 'acceleration_rms': 'm/s²',
         'acceleration_peak': 'm/s²', 'kurtosis': '1', 'skewness': '1',
         'low_frequency_impulse': 'm/s²', 'vibration_impulse': 'g'}


def finite(value, label, optional=False):
    if optional and value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(label + '不能是布尔值')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(label + '必须是有限数值') from None
    if not math.isfinite(result):
        raise ValueError(label + '不能是NaN或无穷值')
    return result


def date(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        raise ValueError('时间不是有效ISO格式：' + str(value)[:80]) from None


def members(raw):
    if len(raw) > MAX_ZIP:
        raise ValueError('案例ZIP不能超过20MB')
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(names) > 40 or len(names) != len(set(names)):
                raise ValueError('案例文件数超限或包含重复文件')
            if sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('展开总量不能超过40MB')
            for i in infos:
                p = PurePosixPath(i.filename)
                if i.is_dir():
                    continue
                if (i.flag_bits & 1 or '\\' in i.filename or ':' in i.filename or
                        p.is_absolute() or '..' in p.parts or str(p) != i.filename or
                        ((i.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('不接受加密文件、链接或不安全路径')
            return {i.filename: z.read(i) for i in infos if not i.is_dir()}
    except (BadZipFile, RuntimeError, NotImplementedError, OSError):
        raise ValueError('ZIP损坏或格式不支持') from None


def parse_real(data):
    try:
        c = json.loads(data['case.json'].decode('utf-8-sig'))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('缺少有效UTF-8 case.json') from None
    if not isinstance(c, dict) or c.get('schema_version') != '1.1' or c.get('data_type') != 'real_measurement':
        raise ValueError('真实数据须使用schema_version="1.1"、data_type="real_measurement"')
    for key in ['device','point','operating_condition','latest_acquisition']:
        if not isinstance(c.get(key),dict):
            raise ValueError(key+'必须是对象')
    if not isinstance(c.get('limitations',[]),list) or not all(isinstance(v,str) for v in c.get('limitations',[])):
        raise ValueError('limitations必须是文字列表')
    datasets = c.get('datasets')
    if not isinstance(datasets, list) or not 1 <= len(datasets) <= 16:
        raise ValueError('datasets须为1到16组数据')
    expected = {'case.json'}
    parsed = []
    for d in datasets:
        if not isinstance(d, dict):
            raise ValueError('数据集描述必须是对象')
        for key in ['x_axis','y_axis','acquisition']:
            if not isinstance(d.get(key),dict):
                raise ValueError('数据集'+key+'必须是对象')
        if d.get('sampling') is not None and not isinstance(d['sampling'],dict):
            raise ValueError('sampling必须是对象或null')
        if not isinstance(d.get('name'),str) or not 1<=len(d['name'])<=120:
            raise ValueError('数据集名称缺失或过长')
        path = d.get('data_file', '')
        p = PurePosixPath(path)
        if not isinstance(path,str) or not path.startswith('data/') or p.suffix != '.csv' or len(p.parts) != 2 or path in expected:
            raise ValueError('数据文件必须位于data目录，且不能重复')
        expected.add(path)
        if path not in data:
            raise ValueError('缺少数据文件：' + path)
        raw = data[path]
        if hashlib.sha256(raw).hexdigest() != d.get('data_sha256'):
            raise ValueError('数据文件校验值不一致：' + path)
        try:
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            if reader.fieldnames != ['source_row', 'x', 'y']:
                raise ValueError('CSV列须为source_row,x,y：' + path)
            rows = []
            for r in reader:
                if len(rows) >= 200000 or None in r or any(v is None or v == '' for v in r.values()):
                    raise ValueError('CSV行数超限或含缺失值：' + path)
                finite(r['y'], path + '.y')
                if not r['source_row'].isdigit() or int(r['source_row']) < 1:
                    raise ValueError('原始行号无效：' + path)
                rows.append(r)
        except UnicodeDecodeError:
            raise ValueError('CSV必须使用UTF-8编码') from None
        if not rows or len(rows) != d.get('row_count'):
            raise ValueError('数据行数与声明不一致：' + path)
        parsed.append({**d, 'rows': rows})
    if set(data) != expected:
        raise ValueError('真实数据包只允许case.json及datasets引用的CSV，不接受程序或其他附件')
    device = c.get('device', {})
    point = c.get('point', {})
    operating = c.get('operating_condition', {})
    d = {'id': device.get('device_id'), 'name': device.get('device_name'),
         'device_code': device.get('device_code'),
         'region_name': device.get('region_name') or device.get('location'),
         'measure_point_name': point.get('measure_point_name'),
         'type': device.get('device_type'), 'model': device.get('model'),
         'location': device.get('location'), 'component': point.get('component_raw'),
         'point_id': point.get('local_point_id'), 'point_name': point.get('name_raw'),
         'direction': point.get('direction_name') or point.get('direction_code_raw'),
         'rpm': operating.get('rpm'), 'load': operating.get('load')}
    return {'mode': 'real_measurement', 'case_id': c.get('case_id'), 'title': c.get('case_name'),
            'device': d, 'case_manifest': c, 'datasets': parsed,
            'measured_time': c.get('latest_acquisition', {}).get('measured_time'),
            'sampling_rate': None, 'sample_count': None, 'duration_seconds': None,
            'unit': None, 'history': [], 'waveform': None, 'current_features': {},
            'processing': {'input': '客户最终值及原始坐标，保留数值文本和来源行号',
                           'signal': '不复算特征、不做FFT、不积分；按配置计算规则比值及逐次条件满足情况',
                           'orders': '转速除以60获得参考频率，仅查找精确频率坐标，不提峰、不插值'}}


def check_real(s):
    c = s['case_manifest']
    warnings, limitations = [], list(c.get('limitations', []))
    for key in ['case_id', 'title']:
        if not isinstance(s.get(key), str) or not 1 <= len(s[key]) <= 200:
            raise ValueError('缺少案例编号或名称')
    for key in ['id', 'name', 'point_id', 'point_name']:
        if not isinstance(s['device'].get(key), str) or not s['device'][key].strip():
            raise ValueError('设备或测点必填字段缺失：' + key)
    for key in ['device_code', 'region_name', 'measure_point_name']:
        value = s['device'].get(key)
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 300):
            raise ValueError('台账字段须为非空文本且不超过300字符：' + key)
    rpm = finite(s['device']['rpm'], '转速', True)
    if rpm is not None and rpm < 0:
        raise ValueError('转速不能为负数')
    s['device']['rpm'] = rpm
    rotation = c.get('operating_condition', {}).get('rotational_frequency_hz')
    if rotation is not None and (rpm is None or not math.isclose(finite(rotation, '转频'), rpm / 60, rel_tol=1e-9)):
        raise ValueError('转速与转频不一致')
    if not rpm:
        limitations.append('缺少可信转速，不作倍频坐标对应。')
    ids, files, features = set(), set(), set()
    sources = c.get('sources', [])
    if not isinstance(sources, list) or any(not isinstance(r, dict) for r in sources):
        raise ValueError('来源清单无效')
    source_ids = [r.get('source_id') for r in sources]
    if not all(isinstance(x, str) for x in source_ids) or len(source_ids) != len(set(source_ids)):
        raise ValueError('来源编号缺失或重复')
    for d in s['datasets']:
        kind, code, rows = d.get('kind'), d.get('feature_code'), d['rows']
        if d.get('dataset_id') in ids or not isinstance(d.get('dataset_id'), str):
            raise ValueError('数据集编号缺失或重复')
        ids.add(d['dataset_id']); files.add(d['data_file'])
        if (d.get('device_id') != s['device']['id'] or d.get('point_ref') != s['device']['point_id']
                or d.get('source_id') not in source_ids):
            raise ValueError('数据集与设备、测点或来源不对应')
        if kind == 'trend':
            if code not in UNITS or code in features or d.get('y_axis', {}).get('unit') != UNITS[code]:
                raise ValueError('趋势指标重复、不支持或单位不符合约定')
            features.add(code)
            xs = [date(r['x']) for r in rows]
        elif kind in ['waveform', 'spectrum']:
            if any(v.get('kind') == kind for v in s['datasets'] if v is not d and v['dataset_id'] in ids):
                raise ValueError('暂只接受一组波形和一组频谱')
            if d.get('x_axis', {}).get('unit') != ('s' if kind == 'waveform' else 'Hz') or d.get('y_axis', {}).get('unit') != 'm/s²':
                raise ValueError('波形须为s、m/s²，频谱须为Hz、m/s²，不隐式换算')
            xs = [finite(r['x'], '坐标') for r in rows]
            if xs[0] < 0 or (kind == 'spectrum' and any(float(r['y']) < 0 for r in rows)):
                raise ValueError('时间、频率或谱幅值不能为负')
        else:
            raise ValueError('数据类型仅支持trend、waveform、spectrum')
        try:
            if any(a >= b for a, b in zip(xs, xs[1:])):
                raise ValueError('数据横坐标必须严格递增：' + d['data_file'])
        except TypeError:
            raise ValueError('时间的时区口径不一致') from None
        for axis,key in [('x_axis','first_value'),('x_axis','last_value')]:
            declared=d[axis].get(key)
            expected=rows[0 if key=='first_value' else -1]['x']
            if declared is not None and str(declared)!=expected:
                raise ValueError('横坐标范围声明与实际数据不一致')
        if len({r['source_row'] for r in rows}) != len(rows):
            raise ValueError('同一数据集原始行号重复')
        measured = d.get('acquisition', {}).get('measured_time')
        if measured is not None:
            date(measured)
        if kind == 'waveform':
            p = d.get('sampling') or {}
            fs = finite(p.get('sampling_rate_hz'), '采样频率', True)
            n = finite(p.get('sample_count'), '采样点数', True)
            duration = finite(p.get('duration_seconds'), '采样时长', True)
            if fs is not None and fs <= 0 or duration is not None and duration <= 0:
                raise ValueError('采样频率和时长必须大于零')
            if n is not None and (not n.is_integer() or n != len(rows)):
                raise ValueError('采样点数与波形行数不一致')
            if fs is not None and any(not math.isclose(b-a, 1/fs, abs_tol=max(1e-10, 1/fs*1e-5), rel_tol=0) for a,b in zip(xs,xs[1:])):
                raise ValueError('波形时间步长与采样频率不一致')
            if fs is not None and n is not None and duration is not None and not math.isclose(n/fs, duration, rel_tol=1e-6):
                raise ValueError('点数÷频率与采样时长不一致')
            s.update(sampling_rate=fs, sample_count=int(n) if n is not None else None,
                     duration_seconds=duration, unit=d['y_axis']['unit'], waveform=[float(r['y']) for r in rows])
            if None in [fs,n,duration]:
                limitations.append('波形采样参数不完整，按提供的时间坐标绘图，不推算采样参数。')
    for source in sources:
        if source.get('path'):
            dataset = next((d for d in s['datasets'] if d['data_file'] == source['path']), None)
            if dataset is None or source.get('sha256') != dataset['data_sha256']:
                raise ValueError('来源路径或校验值与数据集不一致')
    charts = c.get('charts', [])
    if not isinstance(charts, list) or len(charts) > 16:
        raise ValueError('图表清单无效或超限')
    if any(not isinstance(ch,dict) or ch.get('dataset_id') not in ids for ch in charts):
        raise ValueError('图表指向不存在的数据集')
    if len({ch.get('chart_id') for ch in charts}) != len(charts):
        raise ValueError('图表编号重复')
    latest = c.get('latest_acquisition') or {}
    if not isinstance(latest.get('dataset_ids',[]),list):
        raise ValueError('最新采集dataset_ids必须是列表')
    if any(x not in ids for x in latest.get('dataset_ids', [])):
        raise ValueError('最新采集引用不存在的数据集')
    if latest.get('measured_time') is not None:
        date(latest['measured_time'])
    else:
        limitations.append('最新图谱的绝对采集时间未提供。')
    if c.get('current_features') is not None:
        raise ValueError('此版真实输入暂使用分数据集的历史特征；current_features请留null，避免未经确认的采集绑定')
    limitations.append('历史记录按用户指定共用最新频谱参考，不代表各历史时刻实测频谱。')
    install = c.get('device', {}).get('installation_date')
    if install:
        install_date = date(install).date()
        if any(d['kind']=='trend' and date(d['rows'][0]['x']).date() < install_date for d in s['datasets']):
            warnings.append('历史数据起始时间早于台账安装日期，请核查台账或数据归属。')
    for kind in ['waveform','spectrum']:
        if not any(d['kind']==kind for d in s['datasets']):
            limitations.append('未提供' + ('波形' if kind=='waveform' else '频谱') + '，不补造对应图表或特征。')
    return {'warnings': list(dict.fromkeys(warnings)), 'limitations': report_limitations(list(dict.fromkeys(limitations))),
            'checked': ['文件校验值', '设备测点关联', '单位', '坐标与时间顺序', '已提供的采样参数', '来源与图表对应'],
            'signal_recalculation': False}


def acquisition_status(datasets):
    """Record proportions, never elapsed-time proportions or a rule prerequisite."""
    d = next((d for d in datasets if d.get('kind') == 'trend' and d.get('feature_code') == 'velocity_rms'), None)
    result = {'threshold': '0.2', 'unit': 'mm/s', 'operator': 'gt',
              'basis': 'record_count', 'note': '按速度有效值记录数统计，非运行时长占比；不作为机理规则前置条件。'}
    if not d or not d.get('rows'):
        return {**result, 'available': False, 'label': '未提供速度有效值，无法统计采集工况',
                'total': 0, 'running_count': 0, 'stopped_count': 0}
    if d['y_axis']['unit'] != 'mm/s':
        raise ValueError('采集工况统计要求速度有效值单位为mm/s，不隐式换算')
    rows = d['rows']
    running = sum(Decimal(r['y']) > Decimal('0.2') for r in rows)
    pct = (Decimal(running) * 100 / len(rows)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    stopped_pct = Decimal('100.00') - pct
    return {**result, 'available': True, 'total': len(rows), 'running_count': running,
            'stopped_count': len(rows)-running, 'running_percent': str(pct),
            'stopped_percent': str(stopped_pct), 'label': f'{pct}%运行＋{stopped_pct}%停机',
            'dataset_id': d['dataset_id'], 'file': d['data_file'], 'source_id': d['source_id'],
            'running_source_rows': [r['source_row'] for r in rows if Decimal(r['y']) > Decimal('0.2')],
            'stopped_source_rows': [r['source_row'] for r in rows if Decimal(r['y']) <= Decimal('0.2')]}


def prepare_real(s):
    q = s['quality']
    evidence, series, orders, chart_manifest = [], [], [], []
    for index, d in enumerate(s['datasets'], 1):
        base = {'dataset_id': d['dataset_id'], 'file': d['data_file'], 'unit': d['y_axis']['unit'],
                'source_id': d['source_id']}
        if d['kind'] == 'trend':
            entry = {**base, 'name': d['name'], 'feature_code': d['feature_code'], 'count': len(d['rows']),
                     'first': d['rows'][0], 'last': d['rows'][-1], 'statistics': d.get('statistics'),
                     'role': '历史特征，不等同于最新图谱的当前特征'}
            series.append(entry)
            for label in ['first','last']:
                evidence.append({**base, 'id': f'EV-{index:02d}-{label.upper()}',
                                 'name': d['name'] + ('历史首值' if label=='first' else '历史末值'),
                                 **entry[label], 'scope': 'history'})
        enabled = next((ch.get('enabled', True) for ch in s['case_manifest'].get('charts', []) if ch['dataset_id']==d['dataset_id']), True)
        if enabled:
            chart_manifest.append({'dataset_id': d['dataset_id'], 'file': f'chart_{index:02d}.png',
                                   'kind': d['kind'], 'title': d['name'], 'unit': d['y_axis']['unit'],
                                   'chart_type':next((ch.get('chart_type','scatter' if d['kind']=='trend' else 'line') for ch in s['case_manifest'].get('charts',[]) if ch['dataset_id']==d['dataset_id']),'scatter' if d['kind']=='trend' else 'line'),
                                   'x_unit': d['x_axis'].get('unit'), 'source': d['data_file']})
    spectrum = next((d for d in s['datasets'] if d['kind']=='spectrum'), None)
    if spectrum and s['device']['rpm']:
        rotation = Decimal(str(s['device']['rpm'])) / Decimal(60)
        by_x = {Decimal(r['x']): r for r in spectrum['rows']}
        for order in [1,2,3,4,6,8,9]:
            hz = rotation * order
            row = by_x.get(hz)
            item = {'order':order, 'hz':float(hz), 'amplitude':row['y'] if row else None,
                    'source_row':row['source_row'] if row else None, 'source_x':row['x'] if row else None,
                    'dataset_id':spectrum['dataset_id'], 'file':spectrum['data_file'],
                    'unit':spectrum['y_axis']['unit'], 'method':'exact_coordinate_lookup',
                    'status':'精确坐标' if row else '无精确坐标，未插值'}
            orders.append(item)
            if row:
                evidence.append({**item,'id':f'EV-ORDER-{order}', 'name':f'{order}X参考频率坐标幅值',
                                 'scope':'latest_spectrum_without_absolute_time'})
    return {'features':{}, 'uploaded_features':{}, 'recomputed_features':{}, 'comparisons':[],
            'feature_source':'客户提供的最终特征值；历史与最新图谱分别展示',
            'missing':q['limitations'], 'warnings':q['warnings'], 'rpm_available':bool(s['device']['rpm']),
            'peaks':[], 'frequency':[], 'amplitude':[], 'series':series, 'order_coordinates':orders,
            'evidence_items':evidence, 'chart_manifest':chart_manifest,
            'acquisition_status': acquisition_status(s['datasets']),
            'signal_recalculation':False, 'history_linked_to_latest':False,
            'spectrum_provided':spectrum is not None,
            'summary':'已按全部历史记录逐次匹配设备机理规则，具体结果见综合判定。'}


def real_decision(s, a, rules):
    # Documents are reference material. No rule is extracted or enabled from their text.
    results = [{'id':r['id'], 'name':r['name'], 'kind':r['kind'], 'source':r['source'],
                'status':'不适用' if r['kind']=='demo_trend' else '待审核，不执行',
                'detail':('真实数据不执行模拟趋势阈值，也不补算趋势增幅。' if r['kind']=='demo_trend' else r['pending'])}
               for r in rules]
    return {'rules':results, 'change_percent':None, 'first':None, 'last':None, 'trend_count':None,
            'trend_start':None, 'trend_end':None, 'data_warnings':a['warnings'],
            'state':'实测资料已整理，故障类型待核实，严重程度未分级',
            'fault':'未定位', 'severity':'未分级', 'requires_review':True,
            'origin':'independent_rules_only', 'final_results_provided':s['case_manifest'].get('final_results')}


def real_facts(s, a, decision):
    return {'mode':s['mode'], 'case_id':s['case_id'], 'device':s['device'],
            'availability':{'raw_waveform_provided':s['waveform'] is not None,
                            'spectrum_provided':a['spectrum_provided'], 'spectrum_computed':False,
                            'chart_images_sent_to_model':False,
                            'raw_waveform_array_omitted_from_prompt':True,
                            'note':'波形及频谱坐标由程序绘图，未向模型发送图片或全量坐标；不能声称目视观察到周期波形或冲击。'},
            'operating_condition':s['case_manifest'].get('operating_condition'),
            'acquisition_status':a.get('acquisition_status'),
            'latest_acquisition':s['case_manifest'].get('latest_acquisition'),
            'historical_features':[{k:v for k,v in x.items() if k not in ['first','last']} for x in a['series']],
            'order_coordinate_lookups':a['order_coordinates'],
            'evidence_items':[x for x in a['evidence_items'] if x.get('scope')!='history'],
            **({'report_spec':writer_report_spec(a['report_plan'])} if 'report_plan' in a else {}),
            'decision':model_decision(decision), 'missing':report_limitations(a['missing']),
            'data_warnings':a['warnings'], 'processing':s['processing'],
            'history_linked_to_latest':False,
            'metric_definition_status':{'kurtosis':'按用户确认，加速度峭度即输入峭度',
                                        'velocity_rms':'按用户确认，通频速度有效值即速度有效值',
                                        'order_amplitude':'频谱对应横坐标的纵坐标，按业务规则求和及相除'},
            'input_scope':'全部历史记录已由程序逐次匹配。提供规则条件、每条件次数统计、最近及最高满足率的完整记录和来源；逐次明细另存CSV，不将首末变化作为故障依据；未发送图像。',
            'spectrum_scope':'倍频表仅列选定频率的原始坐标，不是峰值清单，不能证明全频段主峰。'}


def writer_report_spec(plan):
    # Lossless references to decision.rules avoid copying the same statistics
    # once per chart. Full knowledge and all condition statistics remain present.
    return {'version':plan['version'],'conclusion':plan['conclusion'],
            'directions':[{k:v for k,v in d.items() if k not in ['conditions','condition_summary']} for d in plan['directions']],
            'charts':[{'dataset_id':c['dataset_id'],'kind':c['kind'],'title':c['title'],
                       'related_rules':[{'rule_id':r['rule_id'],'fault':r['fault'],'knowledge_id':r['knowledge_id'],
                                         'conditions':[{'id':x['id'],'name':x['name']} for x in r['conditions']]}
                                        for r in c['related_rules']]} for c in plan['charts']]}


def report_limitations(items):
    # Existing manifests may list optional fields as missing; not rule blockers.
    excluded=['负载','运行状态','峭度','低频冲击','算法口径','指标定义','分级','幅值口径','带宽','测点编码','方向','工况','历史末条','最新记录与波形']
    return [x for x in items if not any(term in x for term in excluded)]


def model_decision(decision):
    result={k:v for k,v in decision.items() if k!='rules'}
    result['rules']=[]
    for r in decision['rules']:
        item={k:v for k,v in r.items() if k not in ['records','latest_assessment','best','source_rule_text','latest_reference']}
        if r.get('best'):
            item['historical_best']=r['best'] if r['best']!=r.get('latest') else '与最近记录相同'
        result['rules'].append(item)
    return result
