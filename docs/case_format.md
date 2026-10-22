# 案例数据包格式

每次报告对应一个设备测点、一个当前采集时间及其历史。仅接受模拟数据，必须明确标注 `simulated: true`。ZIP根目录必须包含以下前三个文件，第四个可选。不接受其他文件、子目录、重复文件及加密ZIP。ZIP最大20MB，展开总量最大40MB。

| 文件 | 内容 |
| --- | --- |
| case.json | 设备台账、测点、转速、采样参数、单位、模拟标记 |
| history.csv | 历史特征，必须按时间严格递增，末行是当前时刻 |
| current_features.csv | 当前特征，恰好一行 |
| waveform.csv | 可选，当前时刻的加速度原始波形 |

## 台账与采样参数

`case.json`示例结构可直接参考下载样例。关键字段如下：

```json
{
  "schema_version": 1,
  "case_id": "SYNTH-stable",
  "title": "稳定对照",
  "simulated": true,
  "device": {
    "id": "DEMO-MOTOR-001", "name": "行走电机", "type": "电动机",
    "model": "模拟电机 M-01", "location": "模拟试验区 / 电机试验台",
    "component": "驱动端", "point_id": "DEMO-DE-H",
    "point_name": "驱动端水平径向", "direction": "水平径向",
    "rpm": 1500, "load": "恒定负载（模拟设定）"
  },
  "measured_time": "2026-10-22T12:00:00",
  "sampling_rate": 6400,
  "sample_count": 12800,
  "duration_seconds": 2,
  "unit": "m/s²",
  "feature_units": {
    "velocity_rms": "mm/s", "acceleration_rms": "m/s²",
    "acceleration_peak": "m/s²", "kurtosis": "1",
    "skewness": "1", "crest_factor": "1"
  }
}
```

台账字段均必填。未知转速使用`null`，零转速也按缺少可信转速处理，不补成默认值。采样频率20～1000000Hz、点数32～200000，时长须满足点数÷频率。单位当前按约定严格匹配，不隐式转换g、m/s等单位。

所有时间使用ISO 8601，并在同一案例中保持时区口径一致。推荐显式使用`+08:00`。CSV与台账中的案例编号、测点编号及当前采集时间必须对应。

## 特征表与波形

历史表及当前表的表头相同：

```text
case_id,point_id,measured_time,velocity_rms,acceleration_rms,acceleration_peak,kurtosis,skewness,crest_factor
```

允许特征值留空，表示未知，不使用零替代。其他数值必须有限，不接受NaN或无穷值。历史表最大10000行，至少一行；不足两个有效速度点时不计算趋势增幅。当前表严格一行。历史末行必须与当前特征表处于同一时刻；数值差异会提示核查。

波形表头为`time_seconds,acceleration`。时间从零开始、步长为1/采样频率，最后一点位于`(sample_count-1)/sampling_rate`。总点数必须与台账一致。时长定义是采样点数÷采样频率，不是最后一个采样点的时间。

有波形时，程序复算并保留两套特征，差异容差为相对误差1%或绝对误差0.001（各指标自身单位）。超限时显示上传值、复算值并提示核查；当前分析采用复算值，历史趋势保留上传表，不替换、不隐瞒差异。没有波形时，保留上传当前特征，标记未经波形复核；不生成伪波形、频谱或峰值。

信号处理口径：加速度有效值为原信号RMS；峰值为绝对峰值；峭度为中心四阶矩/方差平方，非超额峭度；峰值因子=峰值/RMS；速度由去均值加速度FFT积分，剔除10Hz以下分量，输出mm/s；频谱采用Hann窗、相干增益修正、单边峰值幅度。

## 四组样例

`samples/stable.zip`稳定对照；`rising.zip`速度振动上升；`impulse.zip`包含人为添加的衰减冲击；`missing.zip`移除波形和转速、保留原有特征。

通过`.venv/bin/python scripts/generate_samples.py`重建样例。固定随机种子20261022，14个历史时刻，每行特征均由该时刻合成波形计算，当前表复制对应末行。ZIP只携带当前波形，历史波形由生成脚本重建；一般上传包没有历史原始波形，因此系统只能验证历史的字段和对应关系，不能声称复核了每条历史特征。冲击样例验证信号特征和报告边界，不代表物理轴承故障仿真。
