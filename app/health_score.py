"""Display supplied scores; compare exact timestamps within the newest running segment."""
from datetime import timezone
from decimal import Decimal
from .real_data import date

MAX_COMPARISON_GAP_SECONDS = 1800


def time_key(value):
    t = date(value)
    return t.astimezone(timezone.utc).isoformat() if t.tzinfo else t.isoformat()


def display(value):
    number = Decimal(value)
    rendered = format(number, '.3f').rstrip('0').rstrip('.')
    return ('约' if Decimal(rendered) != number else '') + rendered


def prepare_health_score(datasets):
    health = next((d for d in datasets if d['kind'] == 'health_score'), None)
    if health is None:
        return None
    model = health['health_model']
    result = {'dataset_id': health['dataset_id'], 'model': model,
              'data_origin': health.get('data_origin', 'provided'),
              'data_notice': health.get('data_notice', ''), 'count': len(health['rows']),
              'source': health['data_file'], 'max_comparison_gap_seconds': MAX_COMPARISON_GAP_SECONDS,
              'caption': '评分模型：' + model['model_name'] + (' ' + model['model_version'] if model.get('model_version') else '') + '；算法：' + model['algorithm_name'],
              'status_caption': '计算状态：' + model['calculation_status'] + '；配置：' + model['configuration_name'],
              'note': '健康分数由输入提供，不设置分级阈值；计算状态不代表设备健康结论。',
              'stopped_count': 0, 'unaligned_count': 0, 'aligned_running_count': 0,
              'comparison': None, 'comparison_text': '', 'assessment_text': '', 'summary_text': ''}
    metrics = {}
    for d in datasets:
        if d['kind'] == 'trend' and d['feature_code'] in ('velocity_rms', 'kurtosis'):
            metrics[d['feature_code']] = {time_key(r['x']): r for r in d['rows']}
    segment = []
    for row in health['rows']:
        key = time_key(row['x'])
        velocity = metrics.get('velocity_rms', {}).get(key)
        kurtosis = metrics.get('kurtosis', {}).get(key)
        if velocity is not None and Decimal(velocity['y']) <= Decimal('0.2'):
            result['stopped_count'] += 1
            segment = []
            continue
        if velocity is None or kurtosis is None:
            result['unaligned_count'] += 1
            segment = []
            continue
        result['aligned_running_count'] += 1
        if segment and (date(row['x']) - date(segment[-1]['time'])).total_seconds() > MAX_COMPARISON_GAP_SECONDS:
            segment = []
        segment.append({'time': row['x'], 'score': row['y'], 'velocity_rms': velocity['y'],
                        'kurtosis': kurtosis['y'], 'score_row': row['source_row'],
                        'velocity_row': velocity['source_row'], 'kurtosis_row': kurtosis['source_row']})
    if model['calculation_status'] != 'OK':
        result['comparison_text'] = '评分计算状态未确认有效，健康分数仅按输入展示，不参与特征对比。'
    elif len(segment) < 2:
        result['comparison_text'] = '最近时段缺少可按相同时间对齐的运行记录，暂不比较健康度与振动特征。'
    else:
        first, last = segment[0], segment[-1]
        delta = {k: Decimal(last[k])-Decimal(first[k]) for k in ['score', 'velocity_rms', 'kurtosis']}
        result['comparison'] = {'start': first, 'end': last, 'count': len(segment),
                                'records': segment, 'deltas': {k:str(v) for k,v in delta.items()},
                                'concordant_decline': delta['score'] < 0 and delta['velocity_rms'] > 0 and delta['kurtosis'] > 0}
        period = first['time'] + ' 至 ' + last['time']
        result['comparison_text'] = (period + '的对齐运行记录中，健康度由' + display(first['score']) + '分变为' + display(last['score']) +
                                     '分；速度有效值由' + display(first['velocity_rms']) + '变为' + display(last['velocity_rms']) +
                                     ' mm/s，峭度由' + display(first['kurtosis']) + '变为' + display(last['kurtosis']) + '。')
        result['summary_text'] = ('最近可对齐运行时段的健康度由' + display(first['score']) + '分变为' +
                                  display(last['score']) + '分，评分仅作辅助参考。')
        if result['comparison']['concordant_decline']:
            result['assessment_text'] = '同一对齐时段内，健康度下降，速度有效值与峭度升高，变化方向一致，可作为现场复核的辅助参考；不据此确定故障等级或停机等级。'
        elif delta['score'] < 0:
            result['assessment_text'] = '该时段健康度下降，但速度有效值与峭度未同时上升，不能将二者表述为变化方向一致；故障结论仍依据机理规则。'
        else:
            result['assessment_text'] = '健康度分值作为独立评分结果展示，不替代本次机理规则判定，也不据此推定健康等级。'
    result['comparison_text'] += ' 停机样本不参与健康度对比；不跨停机记录或超过30分钟的采集间隔合并比较。'
    if result['data_origin'] == 'illustrative':
        result['comparison_text'] = '健康度为模拟示例数据。' + result['comparison_text']
        if result['summary_text']:
            result['summary_text'] = '模拟健康分数：' + result['summary_text']
    return result
