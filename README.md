# 设备状态报告生成 Demo

在学校服务器运行的设备报告工作台。上传模拟案例ZIP后，以LangGraph完成输入检查、算法复算、独立规则匹配、全部知识输入、说明撰写、程序绘图和Word/PDF导出。报告沿用提供的八章节Word模板，增加特征核对表和来源信息。

## 使用

1. 启动服务并通过VS Code转发8046端口，打开本地转发地址。本项目已有本机18046端口隧道可用。
2. 在“下载样例数据”中下载稳定对照、振动上升、冲击特征或数据缺失ZIP，再通过“选择案例数据包”上传，点击“导入并检查”。也可以按[案例格式](docs/case_format.md)准备自己的模拟包。
3. 查看台账、采样、波形可用性、上传/复算特征及限制。差异会明确提示；不符合单位、时间对应关系或采样参数的包会被拒绝。
4. 通过页头“知识文档”独立上传DOCX并查看全部条目；通过“诊断规则”独立维护规则，两者互不自动修改。
5. 选择是否使用大模型，生成报告，查看八章节内容并下载Word、PDF及依据。查看“写作输入”可核对完整提示资料。

```bash
cd /data1/tjb/projects/device-report-demo
.venv/bin/python scripts/service.py start
.venv/bin/python scripts/service.py status
# 修改代码后重启
.venv/bin/python scripts/service.py stop
.venv/bin/python scripts/service.py start
```

服务仅监听`127.0.0.1:8046`，保持SSH转发访问；无应用账号体系。服务不自动热重载或开机启动。

## 输入与分析

ZIP包含`case.json`、`history.csv`、`current_features.csv`及可选`waveform.csv`，必须标记模拟数据。四组样例及其生成脚本位于`samples/`、`scripts/generate_samples.py`；每条样例特征均从对应合成波形计算。

有波形时复算特征，按相对误差1%或绝对误差0.001比较。当前分析采用复算值，历史保留上传值，差异全部展示。无波形时保留上传特征和趋势，不生成伪波形或频谱；缺少转速仅限制阶次判断。图表显示模拟标记，报告同步记录来源与限制。

独立趋势规则仅用于演示，不是行业标准。知识文档的轴承规则因低频冲击算法及条件定义尚未确认而禁用。冲击样例并不自动产生故障确诊；故障类型保持未定位，严重程度未分级。未命中规则不能证明设备正常。

## 知识与大模型

DOCX按设备类别、故障章节解析为带编号、现象、原因、措施、规则原文、来源文件与章节的条目。knowledge节点提供当前文档全部条目，不限制设备类别或前四条，暂不实现RAG。

write节点使用设备台账、上传/复算特征、完整历史、趋势统计、频谱峰值、规则结果、缺失与差异、全部知识。模型仅解释与建议，按相关性返回引用编号，不负责诊断、不把典型现象当成本次事实；不写数值，数值由系统填入。完整输入预算超限会明确停止，不截断；API或输出检查失败时使用明确标注的固定文字模板。详细约定见[知识与写作](docs/knowledge_and_writing.md)。

模型配置放在`.env`，参见`.env.example`。当前服务通过API使用`deepseek-flash`，学校服务器运行应用及算法，不运行模型权重。`MODEL_CONTEXT_TOKENS`默认65536，使用UTF-8字节保守估计，配置应与实际模型窗口相符。

## 环境与文件

Python3.11；依赖见`requirements.txt`和锁文件。PDF需要LibreOffice，中文图表需要Noto CJK字体。将八章节报告模板保存为`inputs/reference.docx`，初始知识文档为`inputs/knowledge.docx`，不提交Git。模板哈希与槽位约定见[模板执行约定](docs/template_contract.md)。

主要代码：`case_data.py`解析与校验；`signal_data.py`特征与频谱；`rules.py`独立规则；`knowledge.py`文档解析和完整条目提供；`writer.py`模型输入及检查；`pipeline.py`流程；`export.py`模板导出；`static/`网页。

运行数据位于`workspace/`：上传案例、SQLite任务记录、图表、报告、`snapshot.json`、`evidence.json`及`writer_input.json`。报告保存完整快照，不受后续知识替换影响。当前没有LangGraph节点级断点恢复，重启时未完成任务标记失败。

尚未实现PDM实测接口、行业严重程度分级、完整向量RAG或论文的视觉反馈循环。模型文字检查不能代替专业人工复核。

## 验证与同步

```bash
.venv/bin/python scripts/generate_samples.py
.venv/bin/python -m pytest -q
# 服务启动且模型已配置时，真实API验证四组案例
.venv/bin/python scripts/verify_cases.py
git status
git add app scripts samples tests docs README.md .env.example
git commit -m "Describe the change"
git push
```

仓库为私有，服务器使用仅授权本仓库的部署密钥。不将密钥、输入知识文档、上传包或运行报告提交到GitHub。`samples/`仅包含公开的合成示例。
