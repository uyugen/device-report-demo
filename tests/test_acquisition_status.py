import pytest
from app.real_data import acquisition_status, real_facts
from app.signal_data import analyse
from test_real_input import read, real_zip


def dataset(values):
    return [{'kind':'trend','feature_code':'velocity_rms','dataset_id':'V',
             'data_file':'data/velocity.csv','source_id':'SRC-V','y_axis':{'unit':'mm/s'},
             'rows':[{'x':str(i),'y':v,'source_row':str(i+2)} for i,v in enumerate(values)]}]


def test_threshold_strict_boundary_and_all_records():
    a=acquisition_status(dataset(['0','0.2','0.20000000000000001','10','0.1']))
    assert (a['running_count'],a['stopped_count'],a['total'])==(2,3,5)
    assert a['label']=='40.00%运行＋60.00%停机'
    assert a['running_source_rows']==['4','5']
    assert a['stopped_source_rows']==['2','3','6']
    assert a['basis']=='record_count'


@pytest.mark.parametrize('values,expected', [(['0.2'],'0.00%运行＋100.00%停机'),
    (['1'],'100.00%运行＋0.00%停机'),(['1','0','0'],'33.33%运行＋66.67%停机')])
def test_percentages(values,expected):
    assert acquisition_status(dataset(values))['label']==expected


def test_missing_velocity_is_explicit():
    assert not acquisition_status([])['available']
    assert '无法统计' in acquisition_status(dataset([]))['label']


def test_no_implicit_unit_conversion():
    d=dataset(['1']);d[0]['y_axis']['unit']='m/s'
    with pytest.raises(ValueError,match='mm/s'):acquisition_status(d)


def test_metadata_keeps_business_code_point_and_platform_ids_distinct():
    def change(c,_):
        c['device'].update(device_code='TEST-001',region_name='测试区域')
        c['point']['measure_point_name']='测试电机自由端'
    s=read(real_zip(change));a=analyse(s)
    assert s['device']['id']=='DEVICE' and s['device']['device_code']=='TEST-001'
    assert s['device']['region_name']=='测试区域'
    assert s['device']['measure_point_name']=='测试电机自由端'
    assert s['device']['component']=='电机端' and s['device']['point_name']=='PZ'
    assert a['acquisition_status']['running_count']==1
    assert a['acquisition_status']['total']==2
    assert real_facts(s,a,{ 'rules':[] })['acquisition_status']==a['acquisition_status']


@pytest.mark.parametrize('key',['device_code','region_name','measure_point_name'])
def test_metadata_invalid_types_fail(key):
    def change(c,_):
        c['point' if key=='measure_point_name' else 'device'][key]=123
    with pytest.raises(ValueError,match='台账字段'):read(real_zip(change))
