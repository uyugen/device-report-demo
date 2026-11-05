from copy import deepcopy
import matplotlib.pyplot as plt
import pytest
from app.charts import build_real_figure
from app.health_score import prepare_health_score
from app.health_score import display
from app.reader_report import build_report_plan
from app.signal_data import analyse
from app.mechanism_rules import match_rules
from test_compact_input import compact_zip, read
from test_mechanism_matching import setup_case


def add_health(c, data):
    data['data/health_score.csv'] = ('source_row,x,y\n2,2026-10-23 17:00:00,98.2\n'
                                     '3,2026-10-23 17:30:00,79.3769\n'
                                     '4,2026-10-23 18:00:00,0\n'
                                     '5,2026-10-23 18:30:00,100\n').encode()
    c['datasets'].append({'dataset_id':'HEALTH','kind':'health_score','data_file':'data/health_score.csv','unit':'分',
                          'health_model':{'model_name':'FISH','model_version':'1.0','algorithm_name':'FISHER',
                                          'calculation_status':'OK','configuration_name':'Vibration health V0'},
                          'data_origin':'illustrative','data_notice':'模拟数据，不代表真实健康分数。'})


def sample(change=None):
    def mutate(c,data):
        add_health(c,data)
        if change:change(c,data)
    return read(compact_zip(mutate))


def test_health_values_not_added_to_rule_features_or_acquisition_binding():
    s=sample();a=analyse(s)
    assert s['datasets'][-1]['rows'][1]['y']=='79.3769'
    assert len(a['series'])==1
    assert a['health_score']['model']['calculation_status']=='OK'
    assert '不代表设备健康结论' in a['health_score']['note']
    assert a['acquisition_status']['total']==2
    assert 'HEALTH' not in s['case_manifest']['latest_acquisition']['dataset_ids']


@pytest.mark.parametrize('change,match',[
    (lambda c,d:d.update({'data/health_score.csv':d['data/health_score.csv'].replace(b'79.3769',b'100.01')}),'0到100'),
    (lambda c,d:d.update({'data/health_score.csv':d['data/health_score.csv'].replace(b'79.3769',b'-1')}),'0到100'),
    (lambda c,d:d.update({'data/health_score.csv':d['data/health_score.csv'].replace(b'79.3769',b'nan')}),'NaN'),
    (lambda c,d:c['datasets'][-1].update(unit='mm/s'),'单位'),
    (lambda c,d:c['datasets'][-1]['health_model'].pop('calculation_status'),'calculation_status'),
    (lambda c,d:c['datasets'][-1].pop('data_notice'),'data_notice'),
    (lambda c,d:c['datasets'][-1].update(data_origin='made_up'),'data_origin'),
    (lambda c,d:c['datasets'][-1]['health_model'].update(window_health=90),'不支持字段'),
    (lambda c,d:d.update({'data/health_score.csv':d['data/health_score.csv'].replace(b'17:30',b'17:00')}),'严格递增'),
])
def test_invalid_health_input_rejected(change,match):
    with pytest.raises(ValueError,match=match):sample(change)


def test_health_never_changes_rules_and_is_selected_even_when_normal():
    from app.real_data import writer_report_spec
    s,a,r,k=setup_case();before=match_rules(s,a,r,k)
    s['datasets'].append(sample()['datasets'][-1])
    ch={'dataset_id':'HEALTH','kind':'health_score','file':'health.png','title':'健康度分值'}
    a['chart_manifest']=[ch]
    after=match_rules(s,a,r,k)
    assert before==after
    for rule in after['rules']:
        for key in ['latest_assessment','best']:rule[key]['all_conditions_met']=False
    after['overall_status']='正常'
    plan=build_report_plan(s,a,after,r)
    assert plan['health_chart']==ch and plan['charts']==[]
    assert writer_report_spec(plan)['charts']==[]  # No fake mechanism citation for a supplied health score.


def test_chart_fixed_range_and_original_points_without_thresholds():
    s=sample();a=analyse(s);ch=next(x for x in a['chart_manifest'] if x['kind']=='health_score')
    fig,ax=build_real_figure(s,a,ch)
    try:
        assert ax.get_ylim()==(0,100)
        assert list(ax.lines[0].get_ydata())==[98.2,79.3769,0,100]
        assert len(ax.lines)==1 and not ax.patches
        assert any(t.get_text()=='模拟健康分数' for t in fig.texts)
    finally:plt.close(fig)


def aligned_datasets():
    health=sample()['datasets'][-1]
    times=[f'2026-10-23 17:{m}:00' for m in ['00','05','10','15']]
    health['rows']=[{'source_row':str(i+2),'x':t,'y':str(92-i*9)} for i,t in enumerate(times)]
    datasets=[health]
    for code,ys in [('velocity_rms',['2.2','3','4','7.2']),('kurtosis',['2','3','3.5','4'])]:
        datasets.append({'kind':'trend','feature_code':code,'rows':[
            {'source_row':str(i+2),'x':t,'y':y} for i,(t,y) in enumerate(zip(times,ys))]})
    return datasets


def test_only_exact_running_pairs_support_health_comparison():
    datasets=aligned_datasets();info=prepare_health_score(datasets)
    assert info['comparison']['concordant_decline']
    assert '92分变为65分' in info['comparison_text']
    datasets[1]['rows'][1]['y']='0.2'
    info=prepare_health_score(datasets)
    assert info['stopped_count']==1 and info['comparison']['count']==2
    assert info['comparison']['start']['time'].endswith('17:10:00')
    datasets[2]['rows'][-1]['x']='2026-10-23 17:15:01'
    info=prepare_health_score(datasets)
    assert info['comparison'] is None and info['unaligned_count']==1


def test_big_gap_and_error_status_do_not_create_direction_agreement():
    datasets=aligned_datasets()
    for d in datasets:d['rows'][-1]['x']='2026-10-26 17:15:00'
    assert prepare_health_score(datasets)['comparison'] is None
    datasets=aligned_datasets();datasets[0]['health_model']['calculation_status']='ERROR'
    info=prepare_health_score(datasets)
    assert info['comparison'] is None and '状态未确认有效' in info['comparison_text']


def test_declining_health_with_flat_features_is_not_called_agreement():
    datasets=aligned_datasets()
    for d in datasets[1:]:
        for row in d['rows']:row['y']='3'
    info=prepare_health_score(datasets)
    assert not info['comparison']['concordant_decline']
    assert '不能将二者表述为变化方向一致' in info['assessment_text']


def test_health_display_rounding_is_labelled_and_keeps_original_evidence():
    datasets=aligned_datasets()
    datasets[1]['rows'][0]['y']='12.126785111564354'
    info=prepare_health_score(datasets)
    assert '约12.127' in info['comparison_text']
    assert info['comparison']['start']['velocity_rms']=='12.126785111564354'
    assert display('0')=='0' and display('7.200')=='7.2'
    assert '速度有效值' not in info['summary_text']


def test_unlabelled_health_input_is_neutral_without_test_or_real_claims():
    def change(c,d):
        c.pop('data_type',None)
        c['datasets'][-1].pop('data_origin')
        c['datasets'][-1].pop('data_notice')
    s=sample(change);a=analyse(s)
    assert s['data_origin']=='provided'
    assert a['health_score']['data_origin']=='provided'
    assert '模拟' not in a['health_score']['comparison_text']
    ch=next(c for c in a['chart_manifest'] if c['kind']=='health_score')
    fig,_=build_real_figure(s,a,ch)
    try:
        assert not any(any(word in t.get_text() for word in ['模拟','派生测试','真实采集']) for t in fig.texts)
    finally:plt.close(fig)


def test_writer_cannot_invent_health_explanation():
    from test_reader_report import sample as report_sample
    from app.writer import validate_reader_narrative
    s,a,r,k,d,plan,facts,text=report_sample()
    facts['health_score']={'data_origin':'illustrative'}
    text['mechanism']='健康度持续下降，证明当前发生故障。'
    with pytest.raises(ValueError,match='健康度说明'):
        validate_reader_narrative(text,[x['id'] for x in k],facts)
