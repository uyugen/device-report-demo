import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from pathlib import Path

def draw(snapshot,analysis,out):
    if snapshot.get('mode') == 'real_measurement':
        return draw_real(snapshot, analysis, out)
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    if Path(font).exists():font_manager.fontManager.addfont(font)
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10})
    def finish(fig,ax,name):
        ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
        fig.tight_layout();fig.savefig(out/name,dpi=180,facecolor='white');plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.5,3.65))
    y=[h['velocity_rms'] if h['velocity_rms'] is not None else np.nan for h in snapshot['history']]
    ax.plot(range(len(y)),y,color='#165a72',marker='o',markersize=3)
    ids=range(0,len(y),3);ax.set_xticks(list(ids),[snapshot['history'][i]['measured_time'][5:10] for i in ids])
    ax.set(ylabel='速度有效值 (mm/s)',xlabel='采集日期',title='模拟数据 · 速度有效值趋势')
    finish(fig,ax,'trend.png')
    for name in ['waveform','spectrum']:
        fig,ax=plt.subplots(figsize=(9.5,3.65))
        if snapshot['waveform'] is None:
            ax.text(.5,.5,'模拟数据 · 未提供当前波形，无法生成本图',ha='center',va='center',transform=ax.transAxes,color='#667381')
            ax.set_axis_off()
        elif name=='waveform':
            n=min(len(snapshot['waveform']),int(snapshot['sampling_rate']*.2))
            ax.plot(np.arange(n)/snapshot['sampling_rate']*1000,snapshot['waveform'][:n],color='#165a72',lw=.9)
            ax.set(xlabel='时间 (ms)',ylabel='加速度 (m/s²)',title='模拟数据 · 时域波形（前200 ms）')
        else:
            freq=np.array(analysis['frequency']);amp=np.array(analysis['amplitude']);m=freq<=500
            ax.plot(freq[m],amp[m],color='#165a72',lw=1)
            labelled=[]
            for peak in analysis['peaks']:
                if peak['hz']<=500 and all(abs(peak['hz']-hz)>=30 for hz in labelled):
                    ax.annotate(f'{peak["hz"]:g} Hz',(peak['hz'],peak['amplitude']),xytext=(6,12),textcoords='offset points',
                                bbox={'facecolor':'white','edgecolor':'none','alpha':.85,'pad':1})
                    labelled.append(peak['hz'])
                if len(labelled)==2:break
            ax.set(xlabel='频率 (Hz)',ylabel='加速度峰值幅度 (m/s²)',title='模拟数据 · 幅值频谱（Hann窗）')
            ax.set_ylim(bottom=0,top=max(float(max(amp[m]))*1.25,1e-6))
        finish(fig,ax,name+'.png')
    return ['trend.png','waveform.png','spectrum.png']


CHART_STYLE = 'engineering_v1'


def configure_report_fonts():
    # Use the same CJK face in every output, with a Windows fallback for local QA.
    for path in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                 'C:/Windows/Fonts/msyh.ttc']:
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            return font_manager.FontProperties(fname=path).get_name()
    return 'DejaVu Sans'


def condition_ranges(dataset, chart, analysis):
    """Only draw direct metric conditions of the selected, actually matched rules.

    Ratio and spectrum conditions cannot be represented as a threshold on a
    constituent feature. A band is a single rule condition, never a diagnosis.
    """
    if dataset['kind'] != 'trend':
        return []
    ids = {r['rule_id'] for r in chart.get('related_rules', [])}
    ranges = []
    seen = set()
    for direction in analysis.get('report_plan', {}).get('directions', []):
        if direction['rule_id'] not in ids:
            continue
        for condition in direction['conditions']:
            if condition.get('metric') != dataset.get('feature_code'):
                continue
            bounds = tuple((key, float(condition[key])) for key in ['gte', 'gt', 'lte', 'lt'] if key in condition)
            if not bounds or bounds in seen:
                continue
            seen.add(bounds)
            ranges.append({'bounds': dict(bounds), 'label': '机理条件：' + condition['name']})
    return ranges


def build_real_figure(snapshot, analysis, chart):
    from datetime import datetime
    from matplotlib.dates import AutoDateLocator, DateFormatter
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
    from matplotlib.patches import Patch

    d = next(d for d in snapshot['datasets'] if d['dataset_id'] == chart['dataset_id'])
    health = d['kind'] == 'health_score'
    trend = d['kind'] in ('trend', 'health_score')
    x = [datetime.fromisoformat(r['x']) for r in d['rows']] if trend else [float(r['x']) for r in d['rows']]
    y = [float(r['y']) for r in d['rows']]
    height = 3.3 if analysis.get('report_plan') else 3.65
    fig, ax = plt.subplots(figsize=(9.5, height))
    # Fixed margins preserve legibility and identical geometry across the report.
    fig.subplots_adjust(left=.105, right=.975, top=.76, bottom=.235)
    ink, muted, blue = '#243746', '#64748B', '#245780'
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['bottom', 'left']:
        ax.spines[spine].set(color='#A8B5C1', linewidth=.65)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color='#E3E9EE', linewidth=.6)
    ax.tick_params(axis='both', labelsize=10, colors=muted, length=3, width=.6, pad=5)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
    formatter = ScalarFormatter(useOffset=False)
    formatter.set_powerlimits((-3, 5))
    ax.yaxis.set_major_formatter(formatter)
    ax.margins(x=.018, y=.14)

    # Every line vertex is an original input value. Dense histories omit point
    # symbols, not data, timestamps or the connecting polyline; no smoothing.
    line, = ax.plot(x, y, color=blue, linewidth=1.25, label='采集值（原始点连线）' if trend else '采集值',
                    marker='o' if trend and len(x) <= 40 else None, markersize=2.7,
                    markerfacecolor='white', markeredgewidth=.8,
                    solid_capstyle='butt', solid_joinstyle='round', zorder=3)
    # Disable Matplotlib path simplification so vector output retains all vertices.
    line.get_path().should_simplify = False
    ranges = condition_ranges(d, chart, analysis)
    axis_values = list(y)
    for item in ranges:
        axis_values.extend(item['bounds'].values())
    low, high = min(axis_values), max(axis_values)
    padding = max((high-low)*.13, abs(high)*.06, .1 if high == 0 else 1e-9)
    ax.set_ylim(0 if low >= 0 else low-padding, high+padding)
    if health:
        ax.set_ylim(0, 100)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
    handles = [line]
    for item in ranges:
        bounds = item['bounds']
        lower = bounds.get('gte', bounds.get('gt', ax.get_ylim()[0]))
        upper = bounds.get('lte', bounds.get('lt', ax.get_ylim()[1]))
        ax.axhspan(lower, upper, color='#D5A243', alpha=.10, linewidth=0, zorder=0)
        for value in bounds.values():
            ax.axhline(value, color='#A77B2C', lw=.8, ls=(0, (5, 3)), zorder=2)
        handles.append(Patch(facecolor='#FBF5E8', edgecolor='#A77B2C', linewidth=.7, label=item['label']))

    if trend:
        span = (max(x)-min(x)).total_seconds()
        locator = AutoDateLocator(minticks=5, maxticks=8, tz=x[0].tzinfo)
        ax.xaxis.set_major_locator(locator)
        # Full year avoids ambiguous multi-year histories; hours resolve short runs.
        fmt = '%m-%d\n%H:%M' if span < 2*86400 else ('%Y-%m-%d' if min(x).year != max(x).year else '%m-%d')
        ax.xaxis.set_major_formatter(DateFormatter(fmt, tz=x[0].tzinfo))
        ax.set_xlabel('采集时间' + (f'（{x[0].year}年）' if min(x).year == max(x).year else ''), fontsize=10.5, color=ink, labelpad=7)
    else:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=7))
        ax.set_xlabel('相对时间（s）' if d['kind'] == 'waveform' else '频率（Hz）', fontsize=10.5, color=ink, labelpad=7)
        if d['kind'] == 'spectrum':
            for item in analysis.get('order_coordinates', []):
                if item['order'] in [1, 2, 3] and item['amplitude'] is not None:
                    ax.plot(item['hz'], float(item['amplitude']), marker='o', ms=3,
                            mfc='white', mec=blue, linestyle='none', zorder=4)
                    ax.annotate(f"{item['order']}X", (item['hz'], float(item['amplitude'])),
                                xytext=(4, 6), textcoords='offset points', fontsize=8, color=muted)
            local = [(xx, yy) for xx, yy in zip(x, y) if 0 <= xx <= 500]
            if local and max(x) > 500:
                inset = ax.inset_axes([.57, .43, .40, .52])
                inset.plot([p[0] for p in local], [p[1] for p in local], color=blue, lw=.8)
                inset.set(xlim=(0, 500), ylim=(0, max(p[1] for p in local)*1.2 or 1))
                inset.set_title('低频局部 0–500 Hz', fontsize=8, loc='left', color=muted)
                inset.tick_params(labelsize=7, colors=muted)
                inset.spines[['top', 'right']].set_visible(False)
                inset.yaxis.grid(color='#E3E9EE', linewidth=.5)
    unit = d['y_axis']['unit']
    ax.set_ylabel(d['name'] + ('（无量纲）' if unit in ['1', '无量纲', '-'] else f'（{unit}）'),
                  fontsize=10.5, color=ink, labelpad=8)
    fig.text(.105, .93, d['name'] + ('趋势' if trend else ''), fontsize=12.5, color=ink)
    origin = d.get('data_origin', 'provided') if health else snapshot.get('data_origin', 'provided')
    origin_label = ('模拟健康分数' if origin == 'illustrative' else '派生测试数据' if snapshot.get('is_test_data')
                    else '真实采集数据' if origin == 'real_measurement' else '')
    if origin_label:
        fig.text(.975, .935, origin_label, fontsize=9, color=muted, ha='right')
    ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.015), borderaxespad=0,
              frameon=False, fontsize=9, ncol=2, labelcolor=muted, handlelength=2.3, columnspacing=1.6)
    note = '按实际时间连接采集点，连线不表示间隔内连续实测。' if trend else '按客户提供的原始坐标绘制。'
    if ranges:
        note += ' 阴影仅为单项机理条件，须与同一时刻其余条件联合判定。'
    if health:
        note = '按输入时间连接评分点，未设置健康等级阈值；停机样本不参与特征对比。'
    fig.text(.105, .025, note, fontsize=8.5, color=muted)
    return fig, ax


def draw_real(snapshot, analysis, out):
    style = {'font.family': configure_report_fonts(), 'axes.unicode_minus': False,
             'font.size': 10, 'path.simplify': False, 'svg.fonttype': 'path'}
    with plt.rc_context(style):
        for chart in analysis['chart_manifest']:
            fig, _ = build_real_figure(snapshot, analysis, chart)
            try:
                path = Path(out)/chart['file']
                fig.savefig(path, dpi=300, facecolor='white')
                fig.savefig(path.with_suffix('.svg'), facecolor='white')
            finally:
                plt.close(fig)
    return [ch['file'] for ch in analysis['chart_manifest']]
