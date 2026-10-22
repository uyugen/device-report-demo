# 设备状态报告生成 Demo

在学校服务器运行的设备报告工作台。输入模拟设备台账、同源特征历史与波形，使用 LangGraph 依次完成数据检查、算法计算、规则匹配、机理检索、说明撰写、固定绘图和 Word/PDF 导出。

## 开始使用

```bash
cd /data1/tjb/projects/device-report-demo
source .venv/bin/activate
bash scripts/start.sh
```

服务仅监听 `127.0.0.1:8046`。在 VS Code Remote SSH 的“端口”面板转发8046，再打开本地地址。也可以在本机执行 `ssh -N -L 18046:127.0.0.1:8046 school-report`（使用配套SSH配置）。

## 环境与输入

Python 3.11；依赖见 requirements.txt 和 requirements.lock.txt。服务器使用 `uv pip install --python .venv/bin/python -r requirements.txt`。PDF 导出需要服务器安装 LibreOffice，绘图需要 Noto CJK 字体。

将用户提供的报告模板保存为 `inputs/reference.docx`，机理知识文档保存为 `inputs/knowledge.docx`；这些文档不提交Git。模板必须是已核对的八章节版本，槽位说明见 docs/template_contract.md。服务首次启动会导入知识文档，也可在界面独立上传DOCX。

`.env` 保存模型密钥，可按 `.env.example` 配置。不开启模型时使用固定说明模板，页面和报告依据中明确记录实际模式。开启模型后，仅允许生成机理解释、局限和检维修建议，不改变系统结论或生成数值。模型请求不含原始长波形、平台账号、API密钥。

## 功能与边界

- 四种模拟场景：上升、稳定、缺少转速、缺少当前波形；固定随机种子。
- 特征历史、当前值、波形、频谱来自同一信号；算法口径写入依据文件。
- 两个独立入口：DOCX知识导入与JSON规则配置。
- 演示趋势阈值仅用于流程测试，不是行业标准。知识库轴承规则因算法定义和布尔条件未定而保持待审核，不宣称完成故障确诊。
- 三张确定性图表，保留模板八章节，网页预览、Word/PDF与依据JSON。
- SQLite记录任务状态和执行步骤，重启时将未完成任务标记失败；当前不支持LangGraph节点级断点恢复。
- 不支持PDM实测适配器、轴承特征频率定位、行业严重程度分级或论文完整视觉反馈循环。这些是后续工作。
- 服务用于本地SSH转发演示，无应用账号体系，不应改为公网监听。

## 代码结构

`app/signal_data.py` 模拟和算法；`rules.py` 确定性规则；`knowledge.py` 章节解析和设备过滤检索；`writer.py` 模型适配与检查；`pipeline.py` LangGraph流程；`export.py` 模板槽位及媒体替换；`static/` 网页；`config/rules.json` 演示规则；`workspace/` 私有运行产物。

首版知识量小，采用设备类别过滤检索，不冒称已实现向量RAG。用户资料由数据提供者决定维护和审核。

## 检查和同步

```bash
.venv/bin/python -m pytest -q
git status
git add app config scripts tests docs README.md requirements.txt requirements.lock.txt .env.example .gitignore .vscode
git commit -m "Describe the change"
git push
```

仓库为私有；服务器使用仅授权本仓库的部署密钥。自动同步未启用；Git提交/推送是明确的版本边界，不将输出、原始文件或凭据同步到GitHub。
