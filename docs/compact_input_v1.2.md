# 精简输入包（1.2版）

一个ZIP对应一台设备的一个监测部位。包内仅包含case.json和data/下被引用的CSV；知识DOCX与诊断规则继续从独立入口维护。旧1.1版仍可上传。

## 需要提供什么

| 分组 | 字段 | 要求与用途 |
| --- | --- | --- |
| 案例 | schema_version、case_id、data_type | 必填；版本为字符串"1.2"，编号自行定义；真实采集为real_measurement，派生测试为derived_test |
| 案例 | case_name、data_notice | 名称选填；派生测试必须有5～300字说明，不代表客户真实故障 |
| 设备device | device_id、device_name | 必填，平台ID与名称 |
| 设备device | device_code、region_name | 设备编码、安装区域，建议填写；缺失时报告显示未提供，不用平台ID冒充设备编码 |
| 设备device | device_type、model | 整机类别、型号，选填 |
| 测点point | point_id、measure_point_name、diagnostic_category | 必填；测点编号、报告监测部位、适用规则类别。本案例监测部位为行走电机自由端，诊断类别为电动机 |
| 转速 | rpm | 选填，单位r/min；本案例3000。系统计算50Hz及倍频坐标；未知时省略或null，相关条件无法判定 |
| 图谱时间 | latest_acquisition.measured_time | 选填，ISO时间；未知则省略，不能用历史末条时间代替。只描述最新波形/频谱，不绑定历史特征 |
| 频谱范围 | spectrum_scope | 有频谱时必填shared_latest，明确授权历史共用这一份最新频谱参考，不能称为各历史时刻实测频谱 |
| 数据 | datasets | 必填，1～16组，内容见下表 |

## 每组数据的字段

| 字段 | 要求 |
| --- | --- |
| dataset_id | 必填且唯一，供规则证据与图表关联；原案例DS-01～DS-09沿用 |
| kind | trend（历史特征）、waveform（波形）或spectrum（频谱） |
| feature_code | 趋势必填，从下列七类指标选择；波形、频谱省略 |
| data_file | 必填，例如data/kurtosis.csv；只能引用包内data目录的CSV |
| unit | 必填，纵坐标单位；见下表。横坐标类型与单位由kind确定 |
| source.file_name、source.record_id | 选填，原导出文件名或接口记录编号，用于追溯；未提供时以包内CSV路径为来源 |
| measured_time | 图谱选填，覆盖包级图谱时间；历史特征逐行时间在CSV中填写 |
| sampling | 仅波形选填；sampling_rate_hz、sample_count、duration_seconds已知才填。系统检查参数和坐标一致，不反推缺失值 |

| feature_code | 指标 | unit |
| --- | --- | --- |
| velocity_rms | 速度有效值 | mm/s |
| acceleration_rms | 加速度有效值 | m/s² |
| acceleration_peak | 加速度峰值 | m/s² |
| kurtosis | 峭度（非超额峭度） | 1 |
| skewness | 偏度 | 1 |
| low_frequency_impulse | 低频冲击值 | m/s² |
| vibration_impulse | 振动冲击值 | g |

波形纵坐标为m/s²，横坐标为秒；频谱纵坐标为m/s²，横坐标为Hz。暂不隐式换算单位；缺少某指标就省略整组数据，不伪填零值。

CSV仍使用UTF-8编码，表头为source_row,x,y：source_row是原导出文件行号；趋势x为ISO时间，波形x为相对秒数，频谱x为Hz；y为客户接口或导出的最终值。时间、坐标与数值文本原样保留。横坐标严格递增，同一时刻的不同指标按时间对应；不跨时刻拼接，不插值。

## 系统负责的内容

系统读取CSV行数、坐标范围，记录收到文件的SHA256指纹，生成内部来源编号和图表名称。指纹用于追溯收到的文件，不替代客户来源确认。绘图方式、故障相关图表筛选、机理规则和写作策略由程序配置，客户不在输入包中填写。

采集工况按速度有效值大于0.2mm/s统计运行记录占比；转频按rpm/60计算。系统不复算信号特征、不做FFT、不从频谱提取主峰；规则需要的比值仍逐时刻计算。所有条件同时满足才判定对应故障，缺失证据按现有未知条件逻辑处理。

已删除打包日期及来源说明占位、运行状态/负载占位、重复转频、空当前特征/最终诊断/知识清单、绘图清单、策略开关、重复设备测点关联、手填行数/范围/文件指纹和无值统计字段。1.2版遇到未支持字段明确报错，避免输入被静默忽略。

## 旧包转换

在项目目录执行，输出使用新路径，不覆盖旧包：

```bash
.venv/bin/python scripts/compact_case_package.py old.zip compact.zip
```

转换前后均做结构检查，逐个复制被引用CSV的原始字节，不改写数据；诊断类别从旧显式类别或原监测部位/设备类别沿用。包内不附带转换程序、知识DOCX或预期诊断答案。

本次正常与派生故障包已核对全部CSV原始字节和逐时刻逐条件规则结果，新旧一致：正常104条；派生测试88条正常、16条轴承故障，4张关联特征图。源码测试174项通过。
