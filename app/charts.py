import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from pathlib import Path

def draw(snapshot,analysis,out):
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
