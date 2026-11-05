"""Compact customer input, normalized once into the existing evidence contract."""
import csv
import hashlib
import io

METRIC_NAMES = {
    'velocity_rms': '速度有效值', 'acceleration_rms': '加速度有效值',
    'acceleration_peak': '加速度峰值', 'kurtosis': '峭度', 'skewness': '偏度',
    'low_frequency_impulse': '低频冲击值', 'vibration_impulse': '振动冲击值',
}


def fields(value, allowed, required, label):
    if not isinstance(value, dict):
        raise ValueError(label + '必须是对象')
    unknown = set(value) - set(allowed)
    if unknown:
        raise ValueError(label + '含不支持字段：' + ', '.join(sorted(unknown)))
    for key in required:
        if not isinstance(value.get(key), str) or not value[key].strip() or len(value[key]) > 300:
            raise ValueError(label + '.' + key + '须为非空文本且不超过300字符')
    return value


def normalize_compact(c, data):
    """Derive packaging metadata, never measured values or signal features."""
    fields(c, ['schema_version', 'case_id', 'case_name', 'data_type', 'data_notice',
               'device', 'point', 'rpm', 'latest_acquisition', 'spectrum_scope', 'datasets'],
           ['case_id'], 'case.json')
    dev = fields(c.get('device'), ['device_id', 'device_code', 'device_name', 'region_name',
                                  'device_type', 'model'], ['device_id', 'device_name'], 'device')
    point = fields(c.get('point'), ['point_id', 'measure_point_name', 'diagnostic_category'],
                   ['point_id', 'measure_point_name', 'diagnostic_category'], 'point')
    latest = fields(c.get('latest_acquisition', {}), ['measured_time'], [], 'latest_acquisition')
    datasets = c.get('datasets')
    if not isinstance(datasets, list) or not 1 <= len(datasets) <= 16:
        raise ValueError('datasets须为1到16组数据')
    has_spectrum = any(isinstance(d, dict) and d.get('kind') == 'spectrum' for d in datasets)
    if c.get('spectrum_scope') not in (None, 'shared_latest'):
        raise ValueError('当前spectrum_scope仅支持shared_latest（历史共用最新频谱参考）')
    if has_spectrum and c.get('spectrum_scope') != 'shared_latest':
        raise ValueError('须显式设置spectrum_scope=shared_latest，确认历史共用最新频谱参考')
    result = {
        'schema_version': '1.1', 'input_schema_version': '1.2',
        'case_id': c['case_id'], 'case_name': c.get('case_name', dev['device_name'] + '状态分析'),
        'data_type': c.get('data_type', 'provided'), 'data_notice': c.get('data_notice', ''),
        'device': dict(dev),
        'point': {'local_point_id': point['point_id'], 'name_raw': point['measure_point_name'],
                  'measure_point_name': point['measure_point_name'],
                  'diagnostic_category': point['diagnostic_category']},
        'operating_condition': {'rpm': c.get('rpm')},
        'latest_acquisition': {**latest, 'dataset_ids': []},
        'spectrum_scope': c.get('spectrum_scope'), 'datasets': [], 'sources': [],
    }
    for d in datasets:
        fields(d, ['dataset_id', 'kind', 'feature_code', 'data_file', 'unit', 'source',
                   'measured_time', 'sampling', 'health_model', 'data_origin', 'data_notice'], ['dataset_id', 'kind', 'data_file', 'unit'], 'dataset')
        kind, code, path = d['kind'], d.get('feature_code'), d['data_file']
        if kind == 'trend':
            if code not in METRIC_NAMES:
                raise ValueError('趋势须提供受支持的feature_code')
            if d.get('measured_time') is not None or d.get('sampling') is not None:
                raise ValueError('趋势采集时间来自CSV，不填写measured_time或sampling')
        elif kind == 'health_score':
            if code is not None or d.get('measured_time') is not None or d.get('sampling') is not None:
                raise ValueError('健康分数使用CSV逐行时间，不填写feature_code、measured_time或sampling')
            validate_health_metadata(d)
            if d.get('data_origin', 'provided') not in ('provided', 'real_measurement', 'illustrative'):
                raise ValueError('健康分数data_origin须为provided、real_measurement或illustrative')
            if d.get('data_origin') == 'illustrative' and (not isinstance(d.get('data_notice'), str) or not 5 <= len(d['data_notice']) <= 300):
                raise ValueError('示例健康分数须提供data_notice说明')
        elif kind not in ('waveform', 'spectrum') or code is not None:
            raise ValueError('数据类型仅支持trend、waveform、spectrum；图谱不填写feature_code')
        if kind != 'health_score' and any(k in d for k in ['health_model', 'data_origin', 'data_notice']):
            raise ValueError('health_model、data_origin、data_notice仅适用于健康分数')
        if d.get('sampling') is not None:
            fields(d['sampling'], ['sampling_rate_hz', 'sample_count', 'duration_seconds'], [], 'sampling')
            if kind != 'waveform':
                raise ValueError('sampling仅适用于波形')
        source = fields(d.get('source', {}), ['file_name', 'record_id'], [], 'source')
        if any(not isinstance(v, str) or not v.strip() or len(v) > 300 for v in source.values()):
            raise ValueError('source字段须为非空文本且不超过300字符')
        if path not in data:
            raise ValueError('缺少数据文件：' + path)
        try:
            count = 0
            for _ in csv.DictReader(io.StringIO(data[path].decode('utf-8-sig'))):
                count += 1
                if count > 200000:
                    raise ValueError('CSV行数超限：' + path)
        except UnicodeDecodeError:
            raise ValueError('CSV必须使用UTF-8编码') from None
        digest = hashlib.sha256(data[path]).hexdigest()
        sid = 'SRC-' + d['dataset_id']
        item = {
            'dataset_id': d['dataset_id'], 'kind': kind, 'feature_code': code,
            'name': METRIC_NAMES[code] if kind == 'trend' else '健康度分值' if kind == 'health_score' else '时域波形' if kind == 'waveform' else '振动频谱',
            'device_id': dev['device_id'], 'point_ref': point['point_id'],
            'source_id': sid, 'data_file': path, 'data_sha256': digest, 'row_count': count,
            'x_axis': {'unit': None if kind in ('trend', 'health_score') else 's' if kind == 'waveform' else 'Hz'},
            'y_axis': {'unit': d['unit']},
            'acquisition': {'measured_time': d.get('measured_time', latest.get('measured_time')) if kind in ('waveform','spectrum') else None},
            'sampling': d.get('sampling'),
            **({k: d[k] for k in ['health_model', 'data_origin', 'data_notice'] if k in d} if kind == 'health_score' else {}),
        }
        result['datasets'].append(item)
        result['sources'].append({'source_id': sid, 'path': path, 'sha256': digest,
                                  'original_file_name': source.get('file_name', path),
                                  **({'record_id': source['record_id']} if 'record_id' in source else {})})
        if kind in ('waveform', 'spectrum'):
            result['latest_acquisition']['dataset_ids'].append(d['dataset_id'])
    return result


def validate_health_metadata(d):
    fields(d.get('health_model'), ['model_name', 'model_version', 'algorithm_name',
                                   'calculation_status', 'configuration_name'],
           ['model_name', 'algorithm_name', 'calculation_status', 'configuration_name'], 'health_model')
    version = d['health_model'].get('model_version')
    if version is not None and (not isinstance(version, str) or not version.strip() or len(version) > 300):
        raise ValueError('model_version须为非空文本')


def compact_legacy(c):
    """Migrate packaging only; the caller copies every referenced CSV verbatim."""
    if c.get('schema_version') != '1.1':
        raise ValueError('转换源须为1.1版')
    device, point = c['device'], c['point']
    category = point.get('diagnostic_category') or ('电动机' if '电机' in (point.get('component_raw') or '') else device.get('device_type'))
    result = {
        'schema_version': '1.2', 'case_id': c['case_id'], 'data_type': c['data_type'],
        'device': {k: device[k] for k in ['device_id', 'device_code', 'device_name', 'device_type', 'model'] if device.get(k) is not None},
        'point': {'point_id': point['local_point_id'],
                  'measure_point_name': point.get('measure_point_name') or point['name_raw'],
                  'diagnostic_category': category},
        'rpm': c['operating_condition'].get('rpm'), 'datasets': [],
    }
    if device.get('region_name') or device.get('location'):
        result['device']['region_name'] = device.get('region_name') or device['location']
    if c.get('case_name'):
        result['case_name'] = c['case_name']
    if c.get('data_notice'):
        result['data_notice'] = c['data_notice']
    if any(d['kind'] == 'spectrum' for d in c['datasets']):
        result['spectrum_scope'] = 'shared_latest'
    latest = c.get('latest_acquisition', {}).get('measured_time')
    if latest:
        result['latest_acquisition'] = {'measured_time': latest}
    sources = {s['source_id']: s for s in c.get('sources', [])}
    for d in c['datasets']:
        item = {k: d[k] for k in ['dataset_id', 'kind', 'data_file']}
        item['unit'] = d['y_axis']['unit']
        if d['kind'] == 'health_score':
            item.update({k:d[k] for k in ['health_model','data_origin','data_notice'] if k in d})
        if d['kind'] == 'trend':
            item['feature_code'] = d['feature_code']
        measured = d.get('acquisition', {}).get('measured_time')
        if measured:
            item['measured_time'] = measured
        sampling = {k: v for k, v in (d.get('sampling') or {}).items() if v is not None}
        if sampling and d['kind'] == 'waveform':
            item['sampling'] = sampling
        source = sources.get(d.get('source_id'), {})
        if source.get('original_file_name'):
            item['source'] = {'file_name': source['original_file_name']}
        result['datasets'].append(item)
    return result
