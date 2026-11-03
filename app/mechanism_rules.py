"""Evaluate explicit, editable mechanism conditions against every input timestamp.

Amplitude/velocity ratios follow the user's numeric business convention, not a
physical dimensionless energy ratio. Never integrate, square, FFT or interpolate.
"""
import csv
import json
from collections import Counter
from datetime import timezone
from decimal import Decimal, localcontext
from .real_data import date, UNITS


PROFILE = 'mechanism_matching_v2'
MATCHING_MODE = 'all_conditions_required_v1'
POLICY = {
    'aliases': {'加速度峭度':'峭度', '通频速度有效值':'速度有效值'},
    'orders': 'x倍频频率=转速/60×x；幅值或业务用语能量=频谱该横坐标的纵坐标；能量和按纵坐标相加。',
    'ratio': '按用户确认的输入数值口径计算，不做单位换算，不将结果称为无量纲物理能量比。',
    'matching': '历史指标按相同时间逐条对齐；缺值不补齐，不跨时刻拼接条件，不要求运行状态或负载。',
    'scope': '当前配置覆盖机理文档电动机的四类故障；其他设备需在独立入口配置对应条件。',
    'grading': '同一时刻全部条件满足才判为对应故障；任一条件明确不满足则该规则判为正常；无不满足但有未知时无法判定。满足率仅保留为核查计数，不再用于分档、概率或严重程度。',
    'spectrum': '按用户指定，所有历史时刻共用最新频谱的倍频坐标作为规则参考；不代表各历史时刻实测频谱。',
}


def timestamp(value):
    t = date(value)
    return t.astimezone(timezone.utc).isoformat() if t.tzinfo else t.isoformat()


def support(matched, total, failed=None, unknown=0):
    failed=total-matched-unknown if failed is None else failed
    if total and matched==total:return '故障'
    if failed>0:return '正常'
    return '无法判定'


def combine_outcomes(outcomes, blocked=False):
    """OR across fault rules; a failed rule does not cancel another matched rule."""
    if '故障' in outcomes:return '故障'
    if blocked or not outcomes or '无法判定' in outcomes:return '无法判定'
    return '正常'


def validate_mechanism(rule):
    if not all(isinstance(rule.get(k),str) and rule[k].strip() for k in
               ['category','fault','source_rule_text']):raise ValueError('机理规则须有设备类别、故障和规则原文')
    cs=rule.get('conditions')
    if not isinstance(cs,list) or not 1<=len(cs)<=12:raise ValueError('机理条件须为1到12项')
    ids=set()
    for c in cs:
        if not isinstance(c,dict) or not isinstance(c.get('id'),str) or c['id'] in ids:
            raise ValueError('条件编号缺失或重复')
        ids.add(c['id'])
        if not isinstance(c.get('name'),str) or not c['name']:raise ValueError('条件名称缺失')
        metric=c.get('metric')
        if metric is not None:
            if metric not in UNITS or 'numerator' in c or 'denominator' in c:raise ValueError('单指标条件无效')
        else:
            n=c.get('numerator',{})
            if not isinstance(n,dict) or c.get('denominator') not in UNITS:raise ValueError('比值条件无效')
            if set(n)=={'feature'}:
                if n['feature'] not in UNITS:raise ValueError('分子指标不支持')
            elif set(n)=={'orders'}:
                orders=n['orders']
                if (not isinstance(orders,list) or not 1<=len(orders)<=12 or len(set(orders))!=len(orders)
                    or any(type(x)!=int or not 1<=x<=20 for x in orders)):raise ValueError('倍频清单无效')
            else:raise ValueError('分子只能为指标或倍频坐标清单')
        bounds=[k for k in ['gt','gte','lt','lte'] if k in c]
        if not bounds or ('gt' in c and 'gte' in c) or ('lt' in c and 'lte' in c):raise ValueError('条件阈值无效')
        for k in bounds:
            if type(c[k]) not in [int,float] or not Decimal(str(c[k])).is_finite():raise ValueError('阈值须为有限数值')
        lower=c.get('gt',c.get('gte'));upper=c.get('lt',c.get('lte'))
        if lower is not None and upper is not None and lower>=upper:raise ValueError('条件区间无效')
    return rule


def summarize(conditions):
    counts=Counter(c['status'] for c in conditions)
    m,f,u=counts['满足'],counts['不满足'],counts['无法判定']
    n=len(conditions)
    return {'matched':m,'failed':f,'unknown':u,'total':n,
            'match_rate':m/n if n else 0,'coverage':(m+f)/n if n else 0,'support':support(m,n,f,u),
            'complete':bool(n and u==0),'all_conditions_met':bool(n and m==n)}


def run_condition(c, values, orders):
    sources=[];reason=[]
    def feature(code):
        x=values.get(code)
        if x is None:reason.append('缺少对应时刻的'+code);return None
        sources.append(x)
        return Decimal(x['value'])
    def numerator(n):
        if 'feature' in n:return feature(n['feature'])
        parts=[]
        for order in n['orders']:
            x=orders.get(order)
            if x is None or x['amplitude'] is None:
                reason.append('未提供本次采集的'+str(order)+'X精确频谱坐标')
            else:
                sources.append({'kind':'spectrum','order':order,'value':x['amplitude'],
                                **{k:x.get(k) for k in ['dataset_id','file','source_row','unit','hz']}})
                parts.append(Decimal(x['amplitude']))
        return sum(parts,Decimal(0)) if len(parts)==len(n['orders']) else None
    with localcontext() as ctx:
        ctx.prec=34
        if c.get('metric'):
            value=feature(c['metric']);expression=str(value) if value is not None else None
        else:
            num=numerator(c['numerator']);den=feature(c['denominator'])
            if den is not None and den<=0:reason.append('分母为零或负数')
            value=num/den if num is not None and den is not None and den>0 else None
            expression=f'{num} / {den}' if value is not None else None
        ok=value is not None and all({'gt':lambda x,y:x>y,'gte':lambda x,y:x>=y,
                                      'lt':lambda x,y:x<y,'lte':lambda x,y:x<=y}[k](value,Decimal(str(c[k])))
                                     for k in ['gt','gte','lt','lte'] if k in c)
        return {'id':c['id'],'name':c['name'],'status':'无法判定' if value is None else '满足' if ok else '不满足',
                'value':str(value) if value is not None else None,'expression':expression,
                'thresholds':{k:c[k] for k in ['gt','gte','lt','lte'] if k in c},
                'sources':sources,'reason':'；'.join(reason)}


def match_rules(s,a,rules,knowledge):
    # A deliberate structured configuration executes; uploading a document never enables code.
    timeline={};data_rows={}
    for d in s['datasets']:
        if d['kind']!='trend':continue
        for row in d['rows']:
            t=timestamp(row['x'])
            source={'kind':'feature','feature_code':d['feature_code'],'value':row['y'],
                    'time':row['x'],'file':d['data_file'],'dataset_id':d['dataset_id'],
                    'source_row':row['source_row'],'unit':d['y_axis']['unit']}
            timeline.setdefault(t,{})[d['feature_code']]=source
        data_rows[d['feature_code']]=len(d['rows'])
    spectrum=next((d for d in s['datasets'] if d['kind']=='spectrum'),None)
    spectrum_time=(spectrum.get('acquisition',{}).get('measured_time') if spectrum else None)
    if spectrum and not spectrum_time and spectrum['dataset_id'] in s['case_manifest'].get('latest_acquisition',{}).get('dataset_ids',[]):
        spectrum_time=s['case_manifest']['latest_acquisition'].get('measured_time')
    orders={x['order']:x for x in a['order_coordinates']}
    rows=sorted(timeline.items())
    # The monitored motor belongs to a mechanical arm; do not confuse asset class
    # with the component whose mechanism rules are being evaluated.
    category=s['case_manifest'].get('point',{}).get('diagnostic_category')
    category_origin='测点显式诊断类别' if category else '设备类别'
    if not category:
        category=s['device'].get('type')
        if '电机' in (s['device'].get('component') or ''):
            category='电动机';category_origin='监测部位名称包含电机，应用电动机规则'
    results=[]
    for rule in rules:
        if rule['kind']!='mechanism':
            results.append({'id':rule['id'],'kind':rule['kind'],'name':rule['name'],'source':rule['source'],
                            'status':'不适用','detail':'真实数据仅执行结构化机理规则。'})
            continue
        base={k:rule[k] for k in ['id','kind','name','source','category','fault','source_rule_text']}
        source=next((k for k in knowledge if k.get('category')==rule['category'] and k.get('fault')==rule['fault']),None)
        normalized=lambda text:''.join(text.split())
        blocked=('禁用' if not rule['enabled'] else '设备类别不适用' if category!=rule['category']
                 else '来源文档未匹配' if source is None else '来源规则已变化，需核对配置'
                 if normalized(source.get('rule_text',''))!=normalized(rule['source_rule_text']) else None)
        if blocked:
            results.append({**base,'status':blocked,'detail':'未执行；请在独立规则入口核对设备类别、来源与配置。'})
            continue
        executions=[]
        for t,values in rows:
            row_orders=orders
            cs=[run_condition(c,values,row_orders) for c in rule['conditions']]
            executions.append({'scope':'history_shared_latest_spectrum','time':t,'conditions':cs,
                               'spectrum_reference':'shared_latest' if orders else 'missing',**summarize(cs)})
        reference=None
        count=len(executions);complete=sum(x['complete'] for x in executions)
        all_met=sum(x['all_conditions_met'] for x in executions)
        summary=[]
        for c in rule['conditions']:
            cc=[next(v for v in x['conditions'] if v['id']==c['id']) for x in executions]
            summary.append({'id':c['id'],'name':c['name'],**(summarize(cc) if cc else {})})
        best=max(executions,key=lambda x:(x['match_rate'],x['coverage'],x['time']),default=None)
        latest=executions[-1] if executions else None
        current=reference or latest
        detail=f'历史逐次匹配{count}次；可完整判定{complete}次，全部条件符合{all_met}次。'
        if current:detail+=f'最近资料满足{current["matched"]}/{current["total"]}项，不满足{current["failed"]}项，未知{current["unknown"]}项。'
        results.append({**base,'knowledge_id':source['id'],'status':current['support'] if current else '无记录',
                        'detail':detail,'records':executions,'latest_reference':reference,'latest':latest,
                        'best':best,'condition_summary':summary,'record_count':count,
                        'complete_count':complete,'all_met_count':all_met,
                        'all_met_rate':all_met/complete if complete else None,
                        'latest_assessment':current})
    active=[r for r in results if 'records' in r]
    ranked=sorted([r for r in active if r['latest_assessment']],
                  key=lambda r:r['latest_assessment']['match_rate'],reverse=True)
    candidates=[{'rule_id':r['id'],'fault':r['fault'],'knowledge_id':r['knowledge_id'],
                 **{k:r['latest_assessment'][k] for k in ['scope','time','matched','failed','unknown','total','match_rate','support']}}
                for r in ranked if r['latest_assessment']['all_conditions_met']]
    historical_candidates=[{'rule_id':r['id'],'fault':r['fault'],'knowledge_id':r['knowledge_id'],
                            **{k:r['best'][k] for k in ['time','matched','failed','unknown','total','match_rate','support']}}
                           for r in active if r['best'] and r['best']['all_conditions_met']]
    blocked=any(r['status'] not in ['禁用','设备类别不适用','不适用'] and 'records' not in r for r in results)
    overall=combine_outcomes([r['latest_assessment']['support'] for r in active if r['latest_assessment']],blocked)
    state=('判定故障：'+'、'.join(r['fault'] for r in candidates)+'。' if overall=='故障' else
           '当前设备状态正常（本次机理规则判定范围内）。' if overall=='正常' else '当前设备状态无法判定，请核查缺失数据或规则配置。')
    outcomes_by_time={}
    for rule in active:
        for row in rule['records']:outcomes_by_time.setdefault(row['time'],[]).append(row['support'])
    history_outcomes=[{'time':t,'status':combine_outcomes(outcomes,blocked)} for t,outcomes in sorted(outcomes_by_time.items())]
    history_counts=dict(Counter(x['status'] for x in history_outcomes))
    return {'profile':PROFILE,'matching_mode':MATCHING_MODE,'policy':POLICY,'diagnostic_category':category,'category_origin':category_origin,
            'rules':results,'candidates':candidates,'historical_candidates':historical_candidates,
            'state':state,'overall_status':overall,'historical_status_counts':history_counts,
            'historical_status_records':history_outcomes,
            'fault':'、'.join(c['fault'] for c in candidates) or ('无对应故障' if overall=='正常' else '无法判定'),
            'severity':'未分级','requires_review':True,'origin':'configured_mechanism_conditions',
            'historical_time_count':len(rows),'input_record_counts':data_rows,
            'change_percent':None,'first':None,'last':None,'trend_count':len(rows),
            'trend_start':rows[0][0] if rows else None,'trend_end':rows[-1][0] if rows else None,
            'data_warnings':a['warnings']}


def write_matches_csv(decision,path):
    def safe(value):
        text=str(value if value is not None else '')
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['规则编号','故障','范围','时间','满足数','不满足数','未知数','总条件数','条件编号','条件','结果','原值或比值','表达式','数据来源','备注','该规则判定'])
        for r in decision['rules']:
            for row in r.get('records',[])+([r['latest_reference']] if r.get('latest_reference') else []):
                for c in row['conditions']:
                    writer.writerow([safe(v) for v in [r['id'],r['fault'],row['scope'],row['time'],
                        row['matched'],row['failed'],row['unknown'],row['total'],c['id'],c['name'],c['status'],
                        c['value'],c['expression'],json.dumps(c['sources'],ensure_ascii=False),c['reason'] or row.get('note',''),row['support']]])
