"""Reproducible functional test signals; not a physical bearing fault simulator."""
from datetime import datetime, timedelta
import numpy as np
from scipy.signal import find_peaks
import math
from .case_data import FEATURES

SCENARIOS = {
    'rising': '振动逐步上升',
    'stable': '同工况稳定对照',
    'missing_rpm': '缺少转速',
    'missing_waveform': '缺少当前波形',
}

def features(x, fs):
    a = np.asarray(x, dtype=float)
    centered = a - a.mean()
    std = float(np.std(centered))
    acc_rms = float(np.sqrt(np.mean(a*a)))
    peak = float(np.max(np.abs(a)))
    # Explicit frequency-domain integration and 10 Hz high-pass; velocity in mm/s.
    freq = np.fft.rfftfreq(len(a), 1/fs)
    af = np.fft.rfft(centered)
    vf = np.zeros_like(af)
    usable = freq >= 10
    vf[usable] = af[usable]/(2j*np.pi*freq[usable])
    velocity = np.fft.irfft(vf, n=len(a))*1000
    return {
        'velocity_rms':float(np.sqrt(np.mean(velocity**2))),
        'acceleration_rms':acc_rms,
        'acceleration_peak':peak,
        'kurtosis':float(np.mean(centered**4)/std**4) if std else None,
        'skewness':float(np.mean(centered**3)/std**3) if std else None,
        'crest_factor':peak/acc_rms if acc_rms else None,
        'low_frequency_impulse':None,
    }

def simulate(scenario='rising', seed=20261022):
    if scenario not in SCENARIOS:
        raise ValueError('未知模拟场景')
    fs, n, rpm = 6400, 12800, 1500
    t = np.arange(n)/fs
    rng = np.random.default_rng(seed)
    end = datetime(2026,10,22,12,0)
    history=[]; last=None
    for i in range(14):
        target = 2.2 + (1.4*i/13 if scenario!='stable' else 0.04*np.sin(i))
        x = np.sin(2*np.pi*25*t)+0.12*np.sin(2*np.pi*50*t)+0.025*rng.normal(size=n)
        x *= target/features(x,fs)['velocity_rms']
        f=features(x,fs)
        history.append({'measured_time':(end-timedelta(days=13-i)).isoformat(),**f})
        last=x
    return {
        'mode':'simulated','seed':seed,'scenario':scenario,
        'device':{'id':'DEMO-MOTOR-001','name':'行走电机','type':'电动机','model':'演示电机',
                  'location':'演示工厂 / 10号产线 / 16号机器','component':'驱动端',
                  'point_id':'DEMO-DE-H','point_name':'驱动端水平径向','direction':'水平径向',
                  'rpm':None if scenario=='missing_rpm' else rpm,'load':'恒定负载（模拟设定）'},
        'measured_time':end.isoformat(),'sampling_rate':fs,'sample_count':n,
        'duration_seconds':n/fs,'unit':'m/s²','history':history,
        'waveform':None if scenario=='missing_waveform' else last.tolist(),
        'processing':{'velocity':'FFT积分，剔除10 Hz以下成分，输出mm/s',
                      'kurtosis':'中心四阶矩/方差平方，非超额峭度',
                      'peak':'绝对峰值','spectrum':'Hann窗，单边峰值幅度，相干增益修正'},
    }

def analyse(snapshot):
    supplied={k:snapshot.get('current_features',{}).get(k) for k in FEATURES}
    checks=snapshot.get('quality',{'warnings':[],'limitations':[]})
    base={'uploaded_features':supplied,'recomputed_features':{},'comparisons':[],
          'missing':list(checks.get('limitations',[])), 'warnings':list(checks.get('warnings',[])),
          'rpm_available':bool(snapshot['device']['rpm']), 'feature_source':'上传特征表（未经波形复核）'}
    if snapshot['waveform'] is None:
        return {**base,'features':supplied if 'current_features' in snapshot else {},
                'peaks':[],'frequency':[],'amplitude':[]}
    x=np.array(snapshot['waveform']); fs=snapshot['sampling_rate']
    win=np.hanning(len(x)); freq=np.fft.rfftfreq(len(x),1/fs)
    amp=2*np.abs(np.fft.rfft((x-x.mean())*win))/win.sum()
    amp[0]/=2
    if len(x)%2==0:amp[-1]/=2
    ids,_=find_peaks(amp)
    ids=sorted([int(i) for i in ids if freq[i]>=10],key=lambda i:amp[i],reverse=True)[:5]
    computed=features(x,fs)
    for key in FEATURES:
        a,b=supplied[key],computed[key]
        ok=a is not None and b is not None and math.isclose(a,b,rel_tol=.01,abs_tol=.001)
        status='未提供' if a is None else ('一致' if ok else '不一致，请核查')
        base['comparisons'].append({'feature':key,'uploaded':a,'recomputed':b,'status':status})
        if a is not None and not ok:
            base['warnings'].append(f'{key}上传值{a:g}与波形复算值{b:g}不一致，请核查；当前分析采用复算值')
    return {**base,'features':computed,'recomputed_features':computed,'feature_source':'原始波形复算',
            'peaks':[{'hz':float(freq[i]),'amplitude':float(amp[i])} for i in ids],
            'frequency':freq.tolist(),'amplitude':amp.tolist(),
            'missing':base['missing']+['低频冲击值算法口径未定义']}
