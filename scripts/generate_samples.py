"""Rebuild four public synthetic ZIP fixtures from their source waveforms."""
import csv
import io
import json
import sys
from datetime import datetime,timedelta
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.signal_data import features
from app.case_data import FEATURES,META,UNITS

LABELS={'stable':'稳定对照','rising':'振动上升','impulse':'冲击特征','missing':'数据缺失'}


def make_case(kind):
    fs,n=6400,12800
    t=np.arange(n)/fs
    rng=np.random.default_rng(20261022)
    end=datetime(2026,10,22,12)
    history=[];wave=None
    for i in range(14):
        wave=np.sin(2*np.pi*25*t)+.12*np.sin(2*np.pi*50*t)+.025*rng.normal(size=n)
        if kind=='impulse' and i>=10:
            for at in [.13,.47,.81,1.15,1.49,1.83]:
                tau=t-at;mask=(tau>=0)&(tau<.05)
                wave[mask]+=45*np.exp(-120*tau[mask])*np.cos(2*np.pi*180*tau[mask])
        target=2.2+(1.4*i/13 if kind=='rising' else .04*np.sin(i))
        wave*=target/features(wave,fs)['velocity_rms']
        f=features(wave,fs)
        history.append({'case_id':'SYNTH-'+kind,'point_id':'DEMO-DE-H',
                        'measured_time':(end-timedelta(days=13-i)).isoformat(),**{k:f[k] for k in FEATURES}})
    case={'schema_version':1,'case_id':'SYNTH-'+kind,'title':LABELS[kind],'simulated':True,
          'device':{'id':'DEMO-MOTOR-001','name':'行走电机','type':'电动机','model':'模拟电机 M-01',
                    'location':'模拟试验区 / 电机试验台','component':'驱动端','point_id':'DEMO-DE-H',
                    'point_name':'驱动端水平径向','direction':'水平径向','rpm':None if kind=='missing' else 1500,
                    'load':'恒定负载（模拟设定）'},
          'measured_time':end.isoformat(),'sampling_rate':fs,'sample_count':n,'duration_seconds':n/fs,
          'unit':'m/s²','feature_units':UNITS,
          'simulation':{'seed':20261022,'generator':'scripts/generate_samples.py','kind':kind,
                        'note':'历史每行及当前特征均由对应的合成波形计算；missing只移除当前波形与转速，不补造替代数据。'}}
    return case,history,wave


def csv_text(rows,fields):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=fields);w.writeheader();w.writerows(rows)
    return s.getvalue()


def build(dest):
    dest=Path(dest);dest.mkdir(exist_ok=True)
    for kind in LABELS:
        case,h,wave=make_case(kind)
        with ZipFile(dest/f'{kind}.zip','w',ZIP_DEFLATED) as z:
            z.writestr('case.json',json.dumps(case,ensure_ascii=False,indent=2))
            z.writestr('history.csv',csv_text(h,META+FEATURES))
            z.writestr('current_features.csv',csv_text([h[-1]],META+FEATURES))
            if kind!='missing':
                z.writestr('waveform.csv',csv_text(({'time_seconds':i/case['sampling_rate'],'acceleration':float(x)}
                                                  for i,x in enumerate(wave)),['time_seconds','acceleration']))


if __name__=='__main__':build(Path(__file__).resolve().parents[1]/'samples')
