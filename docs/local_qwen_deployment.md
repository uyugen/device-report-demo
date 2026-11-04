# 学校服务器千问本地部署

## 本次配置

模型基座为官方 Qwen/Qwen3.5-9B；Qwen3.5 对应的小规格是9B，不是8B。本次先部署9B，不下载27B。由于学校GPU正在执行其他任务，使用CPU完成本地报告写作验证，不占用GPU显存、不停止其他进程。

使用 unsloth/Qwen3.5-9B-GGUF 的 Q4_K_M 量化权重，文件约5.68GB。量化模型与官方BF16原版精度不同，报告效果以真实案例验证为准。推理引擎为独立编译的 llama.cpp b12065，提供兼容OpenAI的接口。当前仅接收文本资料，未接入图像理解。

| 项目 | 配置 |
| --- | --- |
| 运行目录 | /data1/tjb/qwen-local |
| 权重 | models/Qwen3.5-9B-Q4_K_M.gguf |
| 服务 | http://127.0.0.1:8056/v1 |
| 模型名称 | Qwen3.5-9B-Q4_K_M |
| 推理 | CPU，十二线程，低优先级，单并发 |
| 上下文 | 65536 tokens |
| 生成 | 关闭思考，JSON Schema限制字段及正文数字，沿用现有报告校验 |
| 调用超时 | 每次九百秒，校验失败最多重写一次 |

权重版本固定为 3885219b6810b007914f3a7950a8d1b469d598a5，SHA256为 03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8。模型与运行时清单分别保存在运行目录的 model_manifest.json 和 runtime_manifest.json。权重、密钥和运行日志不提交Git。

## Demo调用

collect → quality → prepare_evidence → rules → knowledge → write → render → validate → export。

write改为调用同一台学校服务器上的模型端口。规则计算、知识入口、全部知识上下文、引用检查、数字检查与Word/PDF模板继续沿用现有流程。llama.cpp正式报告请求采用JSON Schema，约束输出字段、正文数字和图表数量；生成后仍执行语义、引用及长度检查，未放宽判定标准。模型失败只明确回退固定说明，不自动请求DeepSeek或其他外部接口。历史报告仍保留原生成模型。

服务器项目 .env 配置 MODEL_BASE_URL=http://127.0.0.1:8056/v1、MODEL_NAME=Qwen3.5-9B-Q4_K_M、MODEL_API_STYLE=llama_cpp、MODEL_CONTEXT_TOKENS=65536、MODEL_TIMEOUT_SECONDS=900、LLM_ENABLED=true。MODEL_API_KEY使用运行目录api-key文件中的本地随机凭证，不是DeepSeek密钥，不写入源码或说明。服务只绑定127.0.0.1，本地报告资料在学校服务器内处理。

## 使用与运维

在 /data1/tjb/projects/device-report-demo 目录运行：

```bash
.venv/bin/python scripts/local_model_service.py start
.venv/bin/python scripts/local_model_service.py status
.venv/bin/python scripts/service.py start
```

模型启动器只管理其记录的本用户模型进程，端口已占用时不会终止其他服务。查看日志使用 /data1/tjb/qwen-local/logs/server.log。停止本任务模型用 local_model_service.py stop；停止前确认没有报告正在生成。

本机继续访问 http://127.0.0.1:18046/，无需向本机映射模型端口。勾选“使用大模型撰写说明与建议”才调用千问；不勾选仍为固定说明。打开旧报告不会改变旧报告模型。

CPU版本用于验证本地调用和报告效果，速度应以实测为准。可分配GPU后再升级：9B BF16权重约19.3GB，还需为缓存和计算预留显存；建议使用一张空闲48GB A6000。GPU编号须先确认分配，不以瞬时空闲或低利用率为可独占依据。

## 本次验收结果

2026年11月4日已完成真实案例的本地调用与导出验证。最终报告的 writer.mode 为 llm，deployment 为 local，模型为 Qwen3.5-9B-Q4_K_M；未使用固定说明回退，也未请求外部模型接口。

- 全部十六条知识完整传入，输入约一万九千 tokens，没有截断。
- 一百零四个历史时刻及一千三百五十二行条件核查明细与既有规则结果一致；本案例无故障方向，按既有要求不配图。
- 最终一轮约六十四点五秒完成，单次模型输出通过校验，无需重写。这次复用了约一万八千八百 tokens 的输入缓存，不能视为首次请求耗时。
- 首次无缓存的长输入预处理约七分钟，正文生成约每秒五 tokens；重写会增加耗时。性能随服务器负载、资料长度及缓存命中情况变化。
- 当前模型进程常驻内存实测约十点六 GiB；使用十二个 CPU 线程，GPU 显存占用为零。
- 一百三十三项回归测试通过；Word及PDF已导出，Word渲染为一页并完成版式检查。

小模型适配采用有界 JSON Schema、简短写作提醒及生成后校验。校验包括引用、实测数值转写、数据来源、诊断边界和图表对应；失败最多重写一次，仍失败则明确回退固定说明。本次验证覆盖一个真实案例，尚未完成多案例效果对比；报告仍需业务人员复核。

## 官方与实现来源

- 官方基座：https://huggingface.co/Qwen/Qwen3.5-9B
- 量化权重：https://huggingface.co/unsloth/Qwen3.5-9B-GGUF
- 运行时：https://github.com/ggml-org/llama.cpp/tree/b12065

推理服务启动并通过JSON冒烟检查后切换项目配置，再执行真实报告验收。旧配置仅保存于服务器workspace/private_config_backups私有目录，不同步到GitHub。
