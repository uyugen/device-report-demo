import numpy as np
import pytest
from app.signal_data import features,simulate,analyse
from app.rules import evaluate,validate_rules
from app.writer import validate_narrative

def test_known_sine():
    fs=6400;t=np.arange(12800)/fs;x=2*np.sin(2*np.pi*25*t);f=features(x,fs)
    assert f['acceleration_rms']==pytest.approx(2/np.sqrt(2))
    assert f['velocity_rms']==pytest.approx(2000/(2*np.pi*25*np.sqrt(2)))
    assert f['kurtosis']==pytest.approx(1.5)
    assert f['crest_factor']==pytest.approx(np.sqrt(2))
def test_snapshot_coherence():
    s=simulate();a=analyse(s)
    assert a['features']['velocity_rms']==s['history'][-1]['velocity_rms']
    assert a['peaks'][0]['hz']==25
    assert a['peaks'][0]['amplitude']>a['peaks'][1]['amplitude']
def test_missing_rpm_and_waveform():
    assert not analyse(simulate('missing_rpm'))['rpm_available']
    assert analyse(simulate('missing_waveform'))['features']=={}
def test_unreviewed_rule_cannot_enable():
    with pytest.raises(ValueError):validate_rules([{'id':'x','kind':'bearing_draft','enabled':True}])
def test_no_match_is_not_healthy():
    s=simulate('stable');a=analyse(s)
    d=evaluate(s,a,[{'id':'d','name':'test','kind':'demo_trend','enabled':True,'source':'demo','threshold_percent':30}])
    assert '不能据此证明无故障' in d['state']
def test_model_cannot_add_numbers():
    data=dict(mechanism='本次测得温度100度',limitations='当前资料尚不完整',action1='需要进一步检查设备',action2='建议同工况重新测量',citations=['KB-001'])
    with pytest.raises(ValueError):validate_narrative(data,['KB-001'])
def test_model_cannot_forge_citation():
    data=dict(mechanism='周期激励有多种原因',limitations='当前资料尚不完整',action1='需要进一步检查设备',action2='建议同工况重新测量',citations=['FORGED'])
    with pytest.raises(ValueError):validate_narrative(data,['KB-001'])

def test_negated_diagnosis_is_not_a_positive_claim():
    data=dict(mechanism='不能据此确定为轴承故障',limitations='当前资料尚不完整',action1='需要进一步检查设备',action2='建议同工况重新测量',citations=['KB-001'])
    assert validate_narrative(data,['KB-001'])==data
def test_positive_diagnosis_is_rejected():
    data=dict(mechanism='当前确定为轴承故障',limitations='当前资料尚不完整',action1='需要进一步检查设备',action2='建议同工况重新测量',citations=['KB-001'])
    with pytest.raises(ValueError):validate_narrative(data,['KB-001'])
