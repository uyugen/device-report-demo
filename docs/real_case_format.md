# 真实案例输入与使用

学校服务器项目为/data1/tjb/projects/device-report-demo，本地转发地址为http://127.0.0.1:18046/。

## 使用步骤

1. 选择1号电机端1Z_Demo真实输入_3000rpm.zip，点击导入并检查。
2. 核对台账、测点、3000r/min转速、历史特征和图谱；关注安装日期、绝对时间及采集关联提示。
3. 知识文档入口独立上传DOCX，全部条目进入上下文，不使用RAG；独立规则入口不受知识上传影响。
4. 勾选大模型生成机理分析和待核查方向。关闭时采用标明的固定说明，不伪造模型诊断。
5. 查看七类趋势、波形和频谱，下载Word/PDF、依据及写作输入。左侧执行步骤展示实际LangGraph节点。

本版页面、下载API和服务器样例ZIP已移除四组模拟样例；新版上传仅接受真实格式。已有报告保留用于对照。

## ZIP输入

根目录case.json使用schema_version字符串1.1，data_type为real_measurement。data目录仅放datasets引用的CSV；不放程序、参考报告、知识文档或重复原始文件。

case.json的device、point、operating_condition、latest_acquisition、datasets、charts、sources和limitations分别描述台账、测点、工况、采集关联、数据、绘图、来源及缺口。

CSV采用UTF-8，三列表头source_row,x,y。保留原始行号及数值文本；每份文件登记SHA256和记录数。

| 类型 | 指标 | y单位 | x |
| --- | --- | --- | --- |
| trend | velocity_rms | mm/s | ISO格式时间 |
| trend | acceleration_rms、acceleration_peak、low_frequency_impulse | m/s² | ISO格式时间 |
| trend | kurtosis、skewness | 1 | ISO格式时间 |
| trend | vibration_impulse | g | ISO格式时间 |
| waveform | null | m/s² | 相对时间s |
| spectrum | null | m/s² | 频率Hz |

每种指标最多一份，波形和频谱各最多一份。某类缺少可省略对应数据集，不生成替代数据。ZIP最多20MB、展开40MB、40条文件记录、16组数据，单CSV最多200000行。不接受路径越界、加密、链接、重复文件、无穷或NaN。

转速存储于operating_condition.rpm，本案例3000；rotational_frequency_hz为50。未知填null。转速作为图谱参考，不推定历史转速相同。缺少绝对时间、平台采集ID、采样参数时保留null。已提供采样参数时检查点数、频率、时长及坐标一致性；未提供时不反推。

目前历史末条特征与最新图谱未确认关联，current_features留null；历史值与latest_acquisition分别展示。后续客户提供正式采集ID后再增加同次采集当前特征映射。

## 处理与模型边界

流程为collect → quality → prepare_evidence → rules → knowledge → write → render → validate → export。

quality检查文件哈希、字段、单位、设备测点、时间顺序、已提供采样参数及来源。prepare_evidence读取历史首末原值、数量、来源与精确倍频坐标。不复算RMS、峭度、FFT、峰值、能量比或趋势增幅；不将加速度谱m/s²与速度有效值mm/s直接相除。转速除以60及原频谱坐标读取注明来源，不插值、不提峰。

rules只执行独立配置，模拟趋势规则对真实数据不适用，待审核轴承规则不执行。知识文档中的规则只作参考。

write接收每组历史首末值、数量、来源、倍频表、独立规则、限制及全部知识。未向模型发送全量历史曲线或图像，不能声称观察到持续上升、周期波形、冲击形态或全谱主峰。故障假设需引用有效实测编号和知识编号，并保持待核查状态；数值由系统填写，不自动确诊或分级。

上下文预算超限明确停止，不静默截断；API或输出校验失败回退固定模板并标明原因。文字及引用校验不能代替人工专业复核。

## 模板与归档

Word复制用户提供的八章节模板样式和字体，保留页面及表格风格，按九张图扩展正文，替换示例数据与标记。reference.docx的SHA256为3dea2931998ac6034e9f1122aae644e7860e53aa075ebd0fc45a2615b758c402。细节见artifact.md。

workspace/报告编号中归档snapshot.json、evidence.json、writer_input.json、图表、Word和PDF。输入、知识文档、报告、API密钥均不提交GitHub。

```bash
cd /data1/tjb/projects/device-report-demo
.venv/bin/python scripts/service.py status
.venv/bin/python scripts/service.py stop
.venv/bin/python scripts/service.py start
.venv/bin/python -m pytest -q
```

服务监听127.0.0.1:8046，SSH转发到本机18046。继续使用服务器既有API配置，不部署模型权重。自动测试中的信号样例仅验证历史兼容，不提供页面入口。

尚未接正式接口；本版使用ZIP接收客户最终值。采集ID、准确时间、工况、幅值口径、指标定义和分级标准需客户后续补充。

## 本次验证记录

真实案例已通过本地转发访问服务器，使用DeepSeek官方接口deepseek-flash完成模型报告生成；输入包括整理后的证据和全部16条机理知识，不含完整波形或图像。程序通过60项回归测试，最终提示词修改后23项真实输入测试通过。报告包含九张图，Word共七页，已逐页检查。模型提出的故障方向保留待核查状态，未确诊或分级。

模型输出须通过字段、数字和证据引用校验；缺少波形采样参数不等同于缺少波形。被拒绝的模型文字不用于报告正文，仅记录于服务器内部日志，排查时应按客户数据管理。
