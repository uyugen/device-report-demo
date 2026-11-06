# 独立部署与验收

本说明面向首次部署者。先运行不依赖大模型的报告流程，确认知识、规则和导出正常，再接入自有模型接口。部署不需要学校服务器账号、原项目目录、客户数据或任何已有密钥。

## 环境与文件

推荐 Linux、Python 3.11或3.12；以下安装命令以 Ubuntu 24.04 为例。Ubuntu 22.04 需要自行准备兼容的 Python 环境。应用启动脚本和本地模型管理脚本按 Linux 编写，Windows 用户建议使用 WSL2 或 Linux 服务器。

报告应用可先按4核CPU、8 GB内存和5 GB磁盘准备，模型服务资源另计。这是起步配置，不是性能保证。报告生成当前只支持单任务；只运行一个 Uvicorn worker，避免多个进程分别持锁并发写入共享文件。

仓库包含报告模板、部署验收知识 DOCX、三份1.2版案例和独立规则配置。模型权重、运行环境、`.env`、客户输入、上传知识和生成报告不随仓库分发。部署案例的性质与预期结果见[验收资料](../examples/README.md)。

## 安装应用

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip libreoffice-writer fonts-noto-cjk fontconfig poppler-utils
git clone https://github.com/uyugen/device-report-demo.git
cd device-report-demo
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.lock.txt
cp .env.example .env
chmod 600 .env
.venv/bin/python scripts/check_deployment.py --require-pdf
```

私有仓库需要仓库访问权限，使用自己的 GitHub 凭证。没有访问权限时由仓库管理员授权或提供源代码压缩包。已有 `.env` 时不要再次覆盖；示例文件不含可用密钥。

`requirements.lock.txt` 是已验证环境的版本快照。安装失败时先核对 Python、CPU架构、镜像源和报错；如改用 `requirements.txt` 解析依赖，属于新的依赖组合，需要重新运行验收。PDF 导出需要 LibreOffice；中文图表需要 Noto CJK。Word 模板使用微软雅黑，Linux 未安装该字体时可能发生替代和分页差异；有合法字体文件时安装后执行 `fc-cache -f`。不要从不明来源下载字体。

首次验收保持 `.env` 中 `LLM_ENABLED=false`，无需模型或 API key。

## 启动与访问

在项目根目录执行：

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8046 --workers 1
```

前台保留该终端；按 Ctrl+C 关闭。另开终端检查：

```bash
curl --fail http://127.0.0.1:8046/api/health
```

返回 `{"status":"ok","project":"device-report-demo"}` 表示应用已启动。如果应用在远程服务器，在本机新终端建立隧道：

```bash
ssh -N -L 18046:127.0.0.1:8046 用户名@服务器地址
```

本机浏览器打开 `http://127.0.0.1:18046/`。VS Code Remote SSH 也可在端口面板转发8046，再打开实际分配的本地端口。隧道需要保持运行；不要把页面打不开直接判断为应用故障。

已有的 `scripts/service.py start|status|stop` 可用于Linux后台管理，固定监听8046，日志在 `workspace/server.log`。该脚本不提供开机自启，长时间运行应由部署方配置进程管理；不要同时使用两种方式启动同一个端口。模型或 `.env` 改动后，确认没有报告生成任务，再重启应用。

页面没有账号认证和用户隔离；默认只监听回环地址，经 SSH 使用。需要多人对外访问时，先由部署方增加认证、访问控制及 HTTPS，不能直接将8046暴露到公网。

## 手工验收

1. 打开“知识文档”，上传 `examples/deployment_knowledge.docx`，确认识别到4条。上传会替换当前知识库，企业文档先自行备份。
2. 在“诊断规则”查看默认四条电动机规则。知识类别、故障名称、规则原文要与配置匹配；导入文档不会自动修改配置。
3. 上传 `examples/normal.zip`，导入并检查，先不勾选模型写作，生成报告。当前和历史应均为正常，保留规则来源引用，第03节末应有健康度图。
4. 上传 `examples/bearing_fault.zip`，当前应为轴承故障，历史16次正常、8次故障；图文应围绕轴承相关指标组织，健康度图仍排在最后。
5. 上传 `examples/historical_fault.zip`，当前应为正常，历史仍有8次轴承故障，不能写成历史从未异常。
6. 每份报告检查网页、Word和PDF；核对机理引用、中文字符、图表位置、页边距和分页。“核查资料”包含逐次条件明细、输入和执行步骤。

这些案例验证数据接入、规则执行和报告交付流程，不是工业诊断准确率评估。

## 自动验收

在**新的独立目录和端口**运行，避免修改已有企业知识库或打断报告任务。脚本拒绝覆盖内容不同的已导入知识文档。先按上述步骤在新目录完成依赖安装，再启动专用实例：

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8048 --workers 1
```

另一个终端仍位于该新目录：

```bash
.venv/bin/python scripts/smoke_deployment.py --base-url http://127.0.0.1:8048 --require-pdf
```

脚本上传验收知识和三个案例，检查当前与历史结论、四条规则完整执行、健康度图顺序、九个节点和导出文件。结果写入本目录 `workspace/deployment-smoke/results.json`；有任何不符合则非零退出。运行报告与验收结果不提交Git。后端冒烟检查不替代Word/PDF逐页视觉核对。

## 接入模型

**使用自己的兼容接口**：编辑 `.env`，填写可访问的 `MODEL_BASE_URL`、服务实际返回的 `MODEL_NAME`、`MODEL_API_KEY`，并设置 `LLM_ENABLED=true`。`MODEL_CONTEXT_TOKENS` 必须与服务实际上下文一致。不要填写用户历史聊天中的密钥。

**使用本机 Qwen**：按[从空环境部署本地模型](local_model_fresh_install.md)准备。27B与9B仅作为写作服务，规则判定和最终数值不交给模型修改。旧学校服务器管理脚本及其配置仅是已有部署记录，不是通用安装器。

`.env.example` 默认提供本地27B接入字段。9B把地址改为其服务端口，模型名改为实际别名。自有非 llama.cpp 服务要按其协议设置 `MODEL_API_STYLE`；该字段空值走通用JSON请求，`qwen`会关闭思考，`llama_cpp`还会启用本项目的JSON Schema约束。兼容聊天接口不代表一定支持所有扩展参数，应通过新报告验证。

重启应用后检查 `/api/config` 中 `model_enabled` 和 `model_name`，然后勾选模型写作生成新报告。自动验收可增加 `--use-llm`；只要发生固定说明回退，模型验收就失败，不把能下载报告当成模型调用成功。

```bash
.venv/bin/python scripts/smoke_deployment.py --base-url http://127.0.0.1:8048 --require-pdf --use-llm
```

调用外部模型会发送写作输入和完整已导入知识，需由部署方确认数据可外发。选择本机模型时服务地址保持回环地址。模型上下文不足会提示，不能靠调大环境变量冒充真实容量。

## 常见问题与备份

| 现象 | 检查方法 |
| --- | --- |
| 页面打不开 | 服务器先访问 `/api/health`，再核对隧道、本地端口、VPN和端口占用 |
| 模板缺失或版本不匹配 | 执行 `sha256sum inputs/reference.docx`，与[模板约定](template_contract.md)对照；不要另存该Word文件 |
| “来源文档未匹配” | 知识尚未导入，或类别及故障名称与规则不一致 |
| “来源规则已变化” | 知识原文与独立配置不同，需人工核对两者，不能绕过检查 |
| PDF不可用 | 执行 `libreoffice --version`，检查系统库、字体、目录权限和转换日志 |
| 图中中文缺字 | 检查 `fc-match 'Noto Sans CJK SC'` 和Noto字体路径，安装后重启应用 |
| 使用了固定说明 | 查看报告 `writer.mode` 和 `writer.message`；检查模型地址、凭证、上下文、超时和输出校验 |
| 修改规则后结果变化 | 规则是独立业务配置，先审核变更，再用同一输入重新验收 |

迁移时，在无任务运行时备份 `.env`、`config/rules.json`、`inputs/` 和整个 `workspace/`，其中包含知识JSON、SQLite记录及报告文件。备份包含业务数据和密钥，存放在有访问控制的位置，不提交到Git。复制后重新安装依赖并核对模型地址；不要同步其他服务器的GPU编号、PID或私有运行环境。
