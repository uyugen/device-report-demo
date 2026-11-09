# Qwen3.5 27B 本地报告服务

## 模型与范围

基座为 Qwen/Qwen3.5-27B，采用 unsloth/Qwen3.5-27B-GGUF 的 Q4_K_M 四位量化文本权重。量化版本与官方 BF16 原版精度不同，本次仅用于解释规则结果、撰写建议和图下机理含义，不引入模型自主诊断或图像分析。

固定权重版本：3221f178a6b842d04f1fb42f1c413534adcc0a6a。文件为 Qwen3.5-27B-Q4_K_M.gguf，16,740,812,704 字节，SHA256 为 84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806。下载完成后核验整个文件，不只核对分片大小。

## 服务配置

| 项目 | 配置 |
| --- | --- |
| 目录 | /data1/tjb/qwen27-local |
| 接口 | http://127.0.0.1:8057/v1 |
| 模型名 | Qwen3.5-27B-Q4_K_M |
| 运行时 | llama.cpp b12065，本机 CUDA 11.8 编译，架构 sm_86 |
| GPU | 用户明确授权共享物理 GPU 5，RTX A6000 |
| 上下文 | 65536 tokens，单并发 |
| 缓存 | K/V 均为 q8_0，Flash Attention |
| 计算批量 | batch 512，microbatch 128 |
| CPU | 八线程，nice 10 |
| 接口安全 | 仅本机访问，独立随机 API key，文件权限 600 |

官方预编译 CUDA 12.8 包要求较新 GLIBC，与服务器 Ubuntu 22.04 系统库不兼容，因此使用已固定、已核验的 b12065 源码独立构建。不升级系统 GLIBC、驱动或系统 CUDA，不改变9B的CPU运行时。

## 共享资源保护

启动时要求GPU剩余显存至少22528 MiB；单并发、固定上下文、量化缓存与较小microbatch控制常驻及临时需求。守护进程每三秒检查本服务显存，超过20480 MiB或整卡剩余显存低于2048 MiB时，仅停止本用户的27B进程；连续无法读取资源状态也停止本服务。

上述为轮询保护，不是驱动级显存硬隔离或资源预留，不能保证其他进程突然申请显存时完全没有竞争。GPU计算单元未做硬配额，服务可能与同卡任务争用吞吐；不调整其他进程、MPS、显卡功率或全局设置。共享负载影响响应速度。

## 与报告系统的连接

沿用 collect → quality → prepare_evidence → rules → knowledge → write → render → validate → export。仅write使用27B接口；机理判定、全部知识上下文、引用合并、图表和Word模板不变。关闭思考，沿用有界JSON Schema及语义校验；最多重写一次，失败明确回退固定说明，不请求外部模型。

9B接口127.0.0.1:8056保留。模型别名、上下文、超时及密钥通过服务器.env选择，密钥不提交Git。历史报告保留当时模型；查看旧报告不会改成27B，需新建报告验证。正常及故障案例验收后，才切换网页默认模型。

## 运维

在 /data1/tjb/projects/device-report-demo 下执行：

```bash
.venv/bin/python scripts/local_model27_service.py start
.venv/bin/python scripts/local_model27_service.py status
.venv/bin/python scripts/local_model27_service.py stop
```

运行参数位于 config/qwen27_local.json。server.log、resource_status.json、model_manifest.json、runtime_manifest.json在独立运行目录。停止前确认无报告运行。保护触发后需核查资源并手动启动，不循环自动抢占显存。

切回9B时，恢复.env中的本地9B配置及其对应密钥，再重启本项目Demo；不需要停止或卸载27B。私有配置备份在workspace/private_config_backups，不上传GitHub。

## 部署验收（2026-11-05）

正常与派生故障两组案例均通过真实模型调用、业务校验和Word逐页排版检查，网页默认模型已切换到本服务。故障案例为原输入包注入特征后的流程测试，不代表客户真实故障。

| 案例 | 生成耗时 | 历史规则结果 | 导出 |
| --- | --- | --- | --- |
| 正常，20261105_153138_e58f4fd7 | 48.77秒 | 104条正常 | Word/PDF，1页，无故障图表 |
| 派生故障，20261105_153229_aea9da72 | 96.09秒 | 88条正常、16条轴承故障 | Word/PDF，2页，4张关联趋势图 |

正常案例约1.91万输入tokens，未命中提示缓存；故障案例含一次语义校验后的重写，最终请求命中部分缓存。上述为本次共享GPU下的端到端单次记录，不构成公平速度基准，日常耗时会受缓存、重试和同卡负载影响。两组均实际使用27B撰写，未退回固定文案；全部16条知识、1352行逐条件规则核对结果保留。

验收期间本服务显存峰值18256 MiB（约17.8 GiB），整卡剩余12904 MiB（约12.6 GiB）。9B CPU服务仍可用。155项源码测试通过；现有FastAPI生命周期接口有两条弃用提示，不影响本次验收。

## 写作方式与故障排查（2026-11-09）

页面的模型名称表示当前配置，不代表服务一定在线。新建报告需勾选“使用大模型撰写说明与建议”；未勾选时使用固定说明。模型连接失败、上下文超限或输出校验失败时，也可能回退固定说明。查看报告时，页面状态栏按该报告的实际 writer.mode 显示采用模型或固定说明，失败原因保存在 writer.message。打开历史报告不会重新调用模型。

本次排查发现，共享GPU剩余显存过低曾触发保护并停止本服务，造成连接失败。确认资源后，将本服务显存上限从24576 MiB收紧至20480 MiB，启动要求从28672 MiB调整为22528 MiB，整卡最低剩余要求2048 MiB不变；保护机制继续生效。

以原正常案例重新上传并启用模型验证，报告20261109_172325_3409fc90实际采用Qwen3.5-27B-Q4_K_M，输入19738 tokens，输出277 tokens，端到端约60秒，Word/PDF已生成。其正文与此前两份固定说明不同，writer.mode为llm且保留供应商返回的用量记录。

## 来源

- https://huggingface.co/Qwen/Qwen3.5-27B
- https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/tree/3221f178a6b842d04f1fb42f1c413534adcc0a6a
- https://github.com/ggml-org/llama.cpp/tree/b12065
