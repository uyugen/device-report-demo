"""Choose report evidence after matching; retain the full calculation separately."""
from copy import deepcopy

VERSION = 'reader_report_v3'
MIN_REPORT_SUPPORT = .5


def build_report_plan(snapshot, analysis, decision, configured_rules):
    definitions = {r['id']: r for r in configured_rules}
    directions = []
    for rule in decision['rules']:
        latest, best = rule.get('latest_assessment'), rule.get('best')
        if not latest or not best or max(latest['match_rate'], best['match_rate']) < MIN_REPORT_SUPPORT:
            continue
        directions.append({
            'rule_id': rule['id'], 'fault': rule['fault'], 'knowledge_id': rule['knowledge_id'],
            'latest_rate': latest['match_rate'], 'historical_best_rate': best['match_rate'],
            'historical_only': latest['match_rate'] < MIN_REPORT_SUPPORT,
            'priority': best['match_rate'] >= .75,
            'conditions': definitions[rule['id']]['conditions'],
            'condition_summary': rule['condition_summary'],
        })
    directions.sort(key=lambda d: (-d['historical_best_rate'], -d['latest_rate'], d['rule_id']))
    current = [d for d in directions if not d['historical_only']]
    historical = [d for d in directions if d['historical_only']]
    phrases = []
    for d in current:
        prefix = '高度疑似' if d['latest_rate'] == 1 else '疑似' if d['latest_rate'] >= .75 else '存在'
        phrases.append(prefix + d['fault'] + ('的可能' if prefix == '存在' else ''))
    if phrases:
        conclusion = '；'.join(phrases) + '，建议现场复核。'
    else:
        conclusion = '最近记录尚不足以形成明确故障判断。'
    if historical:
        conclusion += '历史记录提示' + '、'.join(d['fault'] for d in historical) + '的可能，需关注复发情况。'
    priority = [d['fault'] for d in directions if d['priority']]
    if priority:
        conclusion += '历史记录中' + '、'.join(priority) + '的支持程度较高，建议优先排查。'
    related_codes, need_spectrum = set(), False
    for d in directions:
        for c in d['conditions']:
            if c.get('metric'):
                related_codes.add(c['metric'])
            else:
                related_codes.add(c['denominator'])
                if 'feature' in c['numerator']:
                    related_codes.add(c['numerator']['feature'])
                if 'orders' in c['numerator']:
                    need_spectrum = True
    selected = []
    datasets = {d['dataset_id']: d for d in snapshot['datasets']}
    available = deepcopy(analysis['chart_manifest'])
    for chart in available:
        dataset = datasets[chart['dataset_id']]
        code = dataset.get('feature_code')
        if not (dataset['kind'] == 'trend' and code in related_codes or
                dataset['kind'] == 'spectrum' and need_spectrum):
            continue
        related = []
        for d in directions:
            conditions = []
            for c in d['conditions']:
                codes = {c.get('metric'), c.get('denominator'), c.get('numerator', {}).get('feature')}
                uses_orders = bool(c.get('numerator', {}).get('orders'))
                if dataset['kind'] == 'trend' and code in codes or dataset['kind'] == 'spectrum' and uses_orders:
                    conditions.append({'id': c['id'], 'name': c['name'],
                                       'history': next(x for x in d['condition_summary'] if x['id'] == c['id'])})
            if conditions:
                related.append({'rule_id': d['rule_id'], 'fault': d['fault'],
                                'knowledge_id': d['knowledge_id'], 'conditions': conditions})
        selected.append({**chart, 'chart_type': 'line', 'related_rules': related})
    return {'version': VERSION, 'conclusion': conclusion, 'directions': directions,
            'charts': selected, 'available_chart_count': len(available),
            'selection_policy': '最近或历史最高规则满足率至少二分之一；展示涉及的全部条件指标，含未满足条件。'
                                '弱支持方向不单独配图，缺少对应输入不补图。此阈值仅控制报告展示，不是诊断阈值。',
            'line_policy': '按原始时间或坐标连接相邻实测点；不插值，不将采集间隔解释为连续实测。'}


def fallback_chart_explanations(plan):
    result = []
    for chart in plan['charts']:
        faults = '、'.join(r['fault'] for r in chart['related_rules'])
        if chart['kind'] == 'spectrum':
            text = '以最新频谱为参考，历史记录的倍频幅值与速度有效值之比用于辨别' + faults + '的相关特征；单一倍频成分不能独立确定故障，需结合其余条件判断。'
        else:
            text = chart['title'] + '是判断' + faults + '的相关指标。应结合幅值比及同一时刻的其余条件判断，单项特征不能独立确定故障。'
        result.append({'dataset_id': chart['dataset_id'], 'text': text,
                       'knowledge_ids': list(dict.fromkeys(r['knowledge_id'] for r in chart['related_rules']))})
    return result
