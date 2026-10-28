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


def draw_real(snapshot, analysis, out):
    from datetime import datetime
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
    font = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    if Path(font).exists():
        font_manager.fontManager.addfont(font)
        plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams.update({'axes.unicode_minus':False, 'font.size':10})
    for chart in analysis['chart_manifest']:
        d = next(d for d in snapshot['datasets'] if d['dataset_id']==chart['dataset_id'])
        x = [datetime.fromisoformat(r['x']) for r in d['rows']] if d['kind']=='trend' else [float(r['x']) for r in d['rows']]
        y = [float(r['y']) for r in d['rows']]
        fig, ax = plt.subplots(figsize=(9.5,3.65))
        if chart.get('chart_type')=='scatter':
            ax.scatter(x,y,color='#2563eb',s=7)
        else:
            ax.plot(x,y,color='#2563eb',lw=.9)
        if d['kind']=='trend':
            locator=AutoDateLocator(minticks=3,maxticks=6)
            ax.xaxis.set_major_locator(locator);ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
        elif d['kind']=='spectrum':
            for item in analysis['order_coordinates']:
                if item['order'] in [1,2,3] and item['amplitude'] is not None:
                    ax.plot(item['hz'],float(item['amplitude']),'o',color='#64748b',ms=3)
            ax.set_ylim(bottom=0)
            local=[(xx,yy) for xx,yy in zip(x,y) if xx<=500]
            if local and x[-1]>500:
                inset=ax.inset_axes([.54,.40,.43,.48])
                inset.plot([p[0] for p in local],[p[1] for p in local],color='#2563eb',lw=.8)
                inset.set(xlim=(0,500),ylim=(0,None),title='低频局部 0–500 Hz')
                inset.tick_params(labelsize=7);inset.title.set_fontsize(8)
                inset.spines[['top','right']].set_visible(False);inset.grid(alpha=.15)
        ax.set(title='真实采集数据 · '+d['name'],xlabel='采集时间' if d['kind']=='trend' else ('相对时间 (s)' if d['kind']=='waveform' else '频率 (Hz)'),
               ylabel=d['name']+' ('+d['y_axis']['unit']+')')
        ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
        fig.tight_layout();fig.savefig(out/chart['file'],dpi=180,facecolor='white');plt.close(fig)
    return [ch['file'] for ch in analysis['chart_manifest']]
