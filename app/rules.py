"""Deterministic rule evaluation, with explicit unknowns and source labels."""
def validate_rules(rules):
    if not isinstance(rules,list) or not rules or len(rules)>30:raise ValueError('规则必须为1到30项的列表')
    ids=set()
    for rule in rules:
        if not isinstance(rule,dict) or not isinstance(rule.get('id'),str) or rule['id'] in ids:raise ValueError('规则ID缺失或重复')
        ids.add(rule['id'])
        if not isinstance(rule.get('name'),str) or not isinstance(rule.get('source'),str):raise ValueError('规则必须有名称和来源')
        if rule.get('kind')=='bearing_draft' and not isinstance(rule.get('pending'),str):raise ValueError('草稿规则必须说明待确认事项')
        if rule.get('kind') not in ['demo_trend','bearing_draft']:raise ValueError('不支持的规则类型')
        if not isinstance(rule.get('enabled'),bool):raise ValueError('enabled必须为布尔值')
        if rule['kind']=='bearing_draft' and rule['enabled']:raise ValueError('轴承规则尚待审核，不能启用')
        if rule['kind']=='demo_trend':
            n=rule.get('threshold_percent')
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not 0<n<=1000:raise ValueError('趋势阈值须在0到1000之间')
    return rules

def evaluate(snapshot,analysis,rules):
    if snapshot.get('mode') == 'real_measurement':
        from .real_data import real_decision
        return real_decision(snapshot, analysis, rules)
    h=[r for r in snapshot['history'] if r.get('velocity_rms') is not None]
    first=h[0]['velocity_rms'] if h else None
    last=h[-1]['velocity_rms'] if h else None
    change=(last-first)/first*100 if first and len(h)>=2 else None
    results=[]
    for rule in rules:
        if rule['kind']=='demo_trend':
            result='未知' if change is None else ('满足' if change>=rule['threshold_percent'] else '不满足')
            results.append({'id':rule['id'],'name':rule['name'],'kind':rule['kind'],'status':result if rule['enabled'] else '禁用',
                'source':rule['source'],'detail':f'速度有效值变化 {change:.1f}%，演示阈值 {rule["threshold_percent"]}%，比较结果：{result}' if change is not None else '有效历史不足或起始值为零，不能计算相对变化'})
        else:
            f=analysis['features']; k=f.get('kurtosis'); c=f.get('crest_factor')
            conditions=[{'name':'3.5≤峭度<4.5','value':k,'status':'未知' if k is None else ('满足' if 3.5<=k<4.5 else '不满足')},
                        {'name':'8≤低频冲击值<16','value':None,'status':'未知'},
                        {'name':'峰值/RMS≥4','value':c,'status':'未知' if c is None else ('满足' if c>=4 else '不满足')}]
            results.append({'id':rule['id'],'name':rule['name'],'kind':rule['kind'],'status':'待审核，不执行','source':rule['source'],
                            'detail':rule['pending'],'conditions':conditions})
    matched=any(r['status']=='满足' for r in results)
    return {'rules':results,'change_percent':change,'first':first,'last':last,
            'trend_count':len(h),'trend_start':h[0]['measured_time'] if h else None,
            'trend_end':h[-1]['measured_time'] if h else None,
            'data_warnings':analysis.get('warnings',[]),
            'state':('达到演示趋势阈值，故障类型待核实' if matched else
                     ('趋势资料不足，不能判断是否达到演示阈值' if change is None else '未达到演示趋势阈值，不能据此证明无故障')),
            'fault':'未定位','severity':'未分级','requires_review':True}
