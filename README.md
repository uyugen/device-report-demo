# 设备状态报告生成工作台

首次安装请从[独立部署与验收](docs/deployment.md)开始。仓库包含Word模板、[部署验收知识文档与三份1.2版案例](examples/README.md)、配置示例及检查脚本；接入本地Qwen见[从空环境安装模型](docs/local_model_fresh_install.md)，验证范围见[部署资料验收记录](docs/deployment_validation.md)。下文的学校服务器记录用于原环境运维，不是新机器的安装前提。

使用客户最终值，按全部历史记录逐时刻匹配电动机机理规则；历史共用用户指定的最新频谱参考。同一规则全部条件满足才判为对应故障，有明确不满足项则该规则正常，无不满足但有未知项时无法判定。不同故障规则独立判断，正常规则不能抵消已命中故障。大模型撰写解释和建议，支持网页、Word、PDF与逐次明细CSV。

当前判定与正常报告说明见 [全条件匹配说明](docs/strict_matching_20261103.md)，实际写作提示词见 [report_writer_prompt.md](docs/report_writer_prompt.md)。

学校服务器本地千问9B的模型来源、资源配置和启动方式见 [本地部署说明](docs/local_qwen_deployment.md)。模型接入使用兼容OpenAI接口，切换模型不改变机理规则判定。

新增27B本地服务使用用户授权的共享GPU 5，资源保护、量化版本及运维见 [27B部署说明](docs/local_qwen27_deployment.md)。9B服务保留，网页当前模型以/api/config及每份报告writer.model为准。

见[使用与规则口径](docs/real_case_format.md)、[模板约定](docs/artifact.md)、[正式报告写作提示词](docs/report_writer_prompt.md)及[本次调整说明](docs/report_revision_20261029.md)。

报告根据当前或历史全部条件满足的故障方向筛选相关特征图，连接原始坐标点，并为每张图编写“机理含义”。正式正文保留结论、台账、图文解释、措施与参考源，全部规则明细和数据检查在网页“核查资料”中查看。模型写作必须通过图表覆盖、对应引用、数字和结论边界检查。

原模拟样例已移除。密钥、客户数据、知识原文和运行报告不入库。

输入包推荐采用[1.2版精简字段](docs/compact_input_v1.2.md)，仅提供台账、明确的诊断类别、转速与数据文件；系统整理元数据，兼容旧1.1版，不改变最终值和机理判定。

新增[健康度分值展示](docs/health_score_display.md)：正常与故障均在第03节末展示0～100分时间曲线，排在相关特征图后。健康分数由输入提供，精确对齐运行记录后生成辅助说明，不改变故障规则，不将模拟评分当作实测或据此推定停机等级。

参考源自动包含实际执行规则的机理条目，正常判定同样保留依据。受控故障测试使用明确标注的派生输入包，见[引用与派生测试说明](docs/report_sources_and_test_data.md)。

## 报告模板

仓库已包含导出程序实际使用的 [Word 模板](inputs/reference.docx)，克隆后保持该路径即可。模板版本、校验命令和替换要求见 [模板执行约定](docs/template_contract.md)。机理知识文档仍需另行导入，PDF 导出仍需安装 LibreOffice 和中文字体。
