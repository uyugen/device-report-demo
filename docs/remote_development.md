# 在本机VS Code中开发服务器项目

服务器目录 `/data1/tjb/projects/device-report-demo`，Python环境 `.venv/bin/python`。本地配套文件为“设备报告Demo_学校服务器.code-workspace”，其Remote SSH别名是school-report。

1. 打开本地配套工作区，等待Remote SSH连接；左下角应显示SSH: school-report。
2. 确认资源管理器中的路径是服务器项目目录；保存文件会直接写入服务器。
3. 终端运行 `source .venv/bin/activate`，通过 `python -m pytest -q` 执行测试。
4. 当前服务由 `python scripts/service.py start` 启动，监听服务器127.0.0.1:8046。修改Python后依次执行 `python scripts/service.py stop` 和 `python scripts/service.py start`；不会自动热更新。
5. 在VS Code端口面板转发8046并打开其本地地址；配套独立SSH隧道提供固定本地地址 http://127.0.0.1:18046。
6. 源码更改经 `git add`、`git commit`、`git push` 同步到私有GitHub仓库。当前并非自动提交、自动推送。

诊断日志为workspace/server.log。服务与隧道关闭后可按以上方法重启；未配置开机自启动。
