"""Choose report evidence after matching; retain the full calculation separately."""
from copy import deepcopy

VERSION = 'reader_report_v3'


def build_report_plan(snapshot, analysis, decision, configured_rules):
    definitions = {r['id']: r for r in configured_rules}
    directions = []
    for rule in decision['rules']:
        latest, best = rule.get('latest_assessment'), rule.get('best')
        if not latest or not best or not (latest['all_conditions_met'] or best['all_conditions_met']):
            continue
        directions.append({
            'rule_id': rule['id'], 'fault': rule['fault'], 'knowledge_id': rule['knowledge_id'],
            'latest_rate': latest['match_rate'], 'historical_best_rate': best['match_rate'],
            'historical_only': not latest['all_conditions_met'],
            'priority': latest['all_conditions_met'],
            'conditions': definitions[rule['id']]['conditions'],
            'condition_summary': rule['condition_summary'],
        })
    directions.sort(key=lambda d: (-d['historical_best_rate'], -d['latest_rate'], d['rule_id']))
    current = [d for d in directions if not d['historical_only']]
    historical = [d for d in directions if d['historical_only']]
    overall=decision.get('overall_status','无法判定')
    conclusion=('当前设备状态正常（本次机理规则判定范围内）。' if overall=='正常' else
                '判定故障：'+'、'.join(d['fault'] for d in current)+'，建议安排现场检查与处理。' if overall=='故障' else
                '当前设备状态无法判定，请核查缺失数据或规则配置。')
    if historical:
        conclusion += '历史记录曾判定' + '、'.join(d['fault'] for d in historical) + '，需关注复发情况。'
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
    health_chart = next((ch for ch in available if ch['kind'] == 'health_score'), None)
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
    return {'version': VERSION, 'matching_mode':decision.get('matching_mode'),
            'rule_citations':list(dict.fromkeys(r['knowledge_id'] for r in decision['rules']
                                               if r.get('records') and r.get('knowledge_id'))),
            'overall_status':overall,'historical_status_counts':decision.get('historical_status_counts',{}),
            'conclusion': conclusion, 'directions': directions,
            'charts': selected, **({'health_chart': health_chart} if health_chart else {}), 'available_chart_count': len(available),
            'selection_policy': '仅为最近或历史某一时刻全部条件满足的故障方向配图；部分满足不作为故障方向，不单独配图。'
                                '健康度分值图独立于故障筛选，正常与故障均在03节末展示；缺少健康分数时说明未提供，不补造曲线。',
            'line_policy': '按原始时间或坐标连接相邻实测点；不插值，不将采集间隔解释为连续实测。'}


def merge_report_citations(text, plan, knowledge):
    """Executed rules are report evidence even when they conclude normal."""
    valid={k['id'] for k in knowledge}
    rule_ids=plan.get('rule_citations',[])
    if not set(rule_ids)<=valid:raise ValueError('已执行规则的知识来源不存在，不能生成无来源引用')
    narrative=list(text.get('citations',[]))
    return {**text,'citations':list(dict.fromkeys([*rule_ids,*narrative]))}, {
        'rules':rule_ids,'narrative':narrative,
        'note':'规则依据包含已执行但未命中故障的条目；引用不表示发生对应故障。'}


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
