import io
import json
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from app.case_data import parse_zip, check_snapshot
from app.input_format import compact_legacy
from app.signal_data import analyse
from test_real_input import real_zip


def compact_zip(change=None):
    with ZipFile(io.BytesIO(real_zip())) as z:
        data = {n: z.read(n) for n in z.namelist()}
    c = compact_legacy(json.loads(data['case.json']))
    if change:
        change(c, data)
    data['case.json'] = json.dumps(c, ensure_ascii=False).encode()
    out = io.BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        for name, raw in data.items():
            z.writestr(name, raw)
    return out.getvalue()


def read(raw):
    s = parse_zip(raw)
    s['quality'] = check_snapshot(s)
    return s


def test_compact_preserves_final_values_and_evidence_coordinates():
    old, new = read(real_zip()), read(compact_zip())
    a, b = analyse(old), analyse(new)
    assert new['case_manifest']['input_schema_version'] == '1.2'
    assert new['case_manifest']['point']['diagnostic_category'] == '电动机'
    for x, y in zip(old['datasets'], new['datasets']):
        assert x['rows'] == y['rows']
        assert x['data_sha256'] == y['data_sha256']
    assert a['order_coordinates'] == b['order_coordinates']
    assert {k:v for k,v in a['acquisition_status'].items() if k != 'source_id'} == {k:v for k,v in b['acquisition_status'].items() if k != 'source_id'}
    assert not b['signal_recalculation']
    assert new['sampling_rate'] is None
    assert 'CSV格式与文件指纹记录' in new['quality']['checked']
    with ZipFile(io.BytesIO(compact_zip())) as z:
        c = json.loads(z.read('case.json'))
    assert not {'charts', 'report_policy', 'sources', 'limitations'} & c.keys()
    assert not {'data_sha256', 'row_count', 'device_id', 'point_ref', 'columns'} & c['datasets'][0].keys()


@pytest.mark.parametrize('change,match', [
    (lambda c,d:c.pop('spectrum_scope'), '显式'),
    (lambda c,d:c.update(spectrum_scope='historical_measured'), 'spectrum_scope'),
    (lambda c,d:c.update(report_policy={'execute_demo_rules':False}), '不支持字段'),
    (lambda c,d:c['point'].pop('diagnostic_category'), 'diagnostic_category'),
    (lambda c,d:c['datasets'][0].update(unit='g'), '单位'),
    (lambda c,d:c['datasets'][0].update(feature_code='other'), 'feature_code'),
    (lambda c,d:c['datasets'][0].update(row_count=999), '不支持字段'),
    (lambda c,d:c['datasets'][0].update(measured_time='2026-01-01'), '趋势采集时间'),
    (lambda c,d:c['datasets'][1].update(sampling={'sample_count':3}), '点数'),
    (lambda c,d:c['datasets'][1].update(sampling={'sampling_rate_hz':500}), '时间步长'),
    (lambda c,d:c['datasets'][1].update(sampling={'sample_count':True}), '布尔'),
    (lambda c,d:c['datasets'][1].update(measured_time='bad'), '时间'),
    (lambda c,d:c['datasets'][0].update(dataset_id=''), '非空'),
    (lambda c,d:d.update({'extra.py':b'bad'}), '其他附件'),
    (lambda c,d:d.update({'data/data1.csv':b'source_row,x,y\n2,bad,1\n'}), '时间'),
])
def test_compact_rejects_invalid_or_ambiguous_inputs(change, match):
    with pytest.raises(ValueError, match=match):
        read(compact_zip(change))


def test_compact_unknown_rpm_keeps_trends_and_marks_order_limit():
    s = read(compact_zip(lambda c,d:c.pop('rpm')))
    a = analyse(s)
    assert a['series'] and not a['order_coordinates']
    assert any('转速' in x for x in a['missing'])


def test_compact_no_spectrum_does_not_require_shared_reference():
    def change(c, data):
        d = c['datasets'].pop()
        data.pop(d['data_file'])
        c.pop('spectrum_scope')
    a = analyse(read(compact_zip(change)))
    assert not a['spectrum_provided'] and not a['order_coordinates']


def test_compact_test_data_still_requires_notice():
    with pytest.raises(ValueError, match='data_notice'):
        read(compact_zip(lambda c,d:c.update(data_type='derived_test')))
    s = read(compact_zip(lambda c,d:c.update(data_type='derived_test', data_notice='派生故障测试，不代表真实故障。')))
    assert s['is_test_data']


def test_compact_omitted_origin_is_neutral_and_preserves_values():
    before=read(compact_zip())
    after=read(compact_zip(lambda c,d:c.pop('data_type')))
    assert after['data_origin']=='provided' and not after['is_test_data']
    assert after['datasets']==before['datasets']
    assert analyse(after)['order_coordinates']==analyse(before)['order_coordinates']


def test_compact_explicit_neutral_origin_is_allowed_but_invalid_origin_is_rejected():
    assert read(compact_zip(lambda c,d:c.update(data_type='provided')))['data_origin']=='provided'
    with pytest.raises(ValueError,match='data_type'):
        read(compact_zip(lambda c,d:c.update(data_type='unrecognized')))
