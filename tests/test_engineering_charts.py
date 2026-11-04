from copy import deepcopy
from datetime import datetime

import matplotlib.pyplot as plt
import pytest
from PIL import Image

from app.charts import build_real_figure, condition_ranges, draw_real


def case(kind='trend'):
    dataset = {'dataset_id': 'D', 'kind': kind, 'name': '峭度', 'feature_code': 'kurtosis',
               'y_axis': {'unit': '1'}, 'rows': [
                   {'x': '2026-10-20T10:00:00', 'y': '0.12'},
                   {'x': '2026-10-20T10:01:00', 'y': '2.75'},
                   {'x': '2026-10-26T12:00:00', 'y': '4.0'}]}
    chart = {'dataset_id': 'D', 'file': 'chart.png', 'related_rules': [{'rule_id': 'R'}]}
    analysis = {'chart_manifest': [chart], 'report_plan': {'directions': [{
        'rule_id': 'R', 'conditions': [{'name': '3.5 ≤ 峭度 < 4.5', 'metric': 'kurtosis', 'gte': 3.5, 'lt': 4.5},
                                     {'name': '峰值 / 有效值 ≥ 4', 'numerator': {'feature': 'acceleration_peak'},
                                      'denominator': 'acceleration_rms', 'gte': 4}]}]}}
    return {'mode': 'real_measurement', 'is_test_data': True, 'datasets': [dataset]}, analysis, chart


def test_irregular_time_and_original_vertices_survive_chart_styling():
    s, a, chart = case()
    before = deepcopy((s, a))
    fig, ax = build_real_figure(s, a, chart)
    try:
        line = ax.lines[0]
        assert list(line.get_ydata()) == [.12, 2.75, 4.0]
        assert list(line.get_xdata()) == [datetime.fromisoformat(r['x']) for r in s['datasets'][0]['rows']]
        assert len(line.get_path().vertices) == 3 and not line.get_path().should_simplify
        assert ax.get_ylim()[1] > 4.5
        assert any('单项机理条件' in t.get_text() for t in fig.texts)
        assert any('派生测试数据' == t.get_text() for t in fig.texts)
        assert (s, a) == before
    finally:
        plt.close(fig)


def test_ratio_condition_never_becomes_constituent_feature_threshold():
    s, a, chart = case()
    dataset = s['datasets'][0]
    assert len(condition_ranges(dataset, chart, a)) == 1
    dataset['feature_code'] = 'acceleration_rms'
    assert condition_ranges(dataset, chart, a) == []
    chart['related_rules'] = [{'rule_id': 'NOT_EXECUTED'}]
    dataset['feature_code'] = 'kurtosis'
    assert condition_ranges(dataset, chart, a) == []
    dataset['kind'] = 'spectrum'
    assert condition_ranges(dataset, chart, a) == []


def test_dense_curve_omits_symbols_without_losing_line_vertices():
    s, a, chart = case()
    s['datasets'][0]['rows'] = [{'x': f'2026-10-20T10:{i:02d}:00', 'y': str(i/10)} for i in range(60)]
    fig, ax = build_real_figure(s, a, chart)
    try:
        assert ax.lines[0].get_marker() == 'None'
        assert len(ax.lines[0].get_path().vertices) == 60
    finally:
        plt.close(fig)


def test_export_has_print_resolution_vector_copy_and_no_global_style_leak(tmp_path):
    s, a, chart = case()
    previous = plt.rcParams['font.size']
    assert draw_real(s, a, tmp_path) == ['chart.png']
    with Image.open(tmp_path/'chart.png') as image:
        assert image.size == (2850, 990)
        assert image.info['dpi'][0] == pytest.approx(300, abs=1)
    assert '<svg' in (tmp_path/'chart.svg').read_text(encoding='utf-8')
    assert plt.rcParams['font.size'] == previous


@pytest.mark.parametrize('kind', ['waveform', 'spectrum'])
def test_signal_charts_keep_all_original_coordinates(kind):
    s, a, chart = case(kind)
    s['datasets'][0]['rows'] = [{'x': '0', 'y': '-.1' if kind == 'waveform' else '.1'},
                               {'x': '50', 'y': '2'}, {'x': '1000', 'y': '.5'}]
    fig, ax = build_real_figure(s, a, chart)
    try:
        assert list(ax.lines[0].get_xdata()) == [0, 50, 1000]
        assert list(ax.lines[0].get_ydata()) == ([-.1, 2, .5] if kind == 'waveform' else [.1, 2, .5])
        assert condition_ranges(s['datasets'][0], chart, a) == []
    finally:
        plt.close(fig)
