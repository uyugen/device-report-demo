# Word 特征表列宽修复

2026-10-23 修复“数据缺口”下方的当前特征表在 Microsoft Word 中被挤成逐字换行的问题。

## 原因与处理

旧实现仅复制模板的固定表格布局属性，未写入总宽度、列网格及单元格宽度。LibreOffice 可以推断布局，但这份不完整的表格几何信息在 Word 中可能被压缩。

新实现根据模板的页面尺寸和页边距计算可用宽度，显式写入 `tblW`、`tblGrid` 及每个单元格的 `tcW`，三者保持一致。特征名称及单位使用较宽列，上传值与波形复算值等宽、右对齐。表头加粗、允许在跨页时重复，每行禁止拆分。

## 已有文件修复

`scripts/repair_feature_table.py` 仅替换已有 DOCX 的该张特征表，不重新调用算法或大模型。除 `word/document.xml` 外，其他包内容保持不变，全文文本保持一致。

默认将修复文件及重新转换的 PDF 写入 `workspace/qa/feature_table_fix/<报告编号>/`，供检查。确认后执行 `--apply` 更新原下载位置，原 Word/PDF 保存在 `workspace/qa/feature_table_backup/<报告编号>/`。已具备完整宽度的表格自动跳过。

```bash
.venv/bin/python scripts/repair_feature_table.py --report-id <报告编号>
.venv/bin/python scripts/repair_feature_table.py --report-id <报告编号> --apply
```

## 验证

- 全部 36 项测试通过，包含两种正文宽度下的表格几何回归检查。
- 稳定对照、振动上升、冲击特征和数据缺失四份报告经 `render_docx.py` 渲染，各三页，共十二页逐页检查通过。
- 核查修复前后文本相同、其他 DOCX 部件未改变。
- 已更新服务端已有的受影响下载文件，并重启服务加载修正后的新报告导出逻辑。

用户已经下载到本机的旧文件不会自动替换，需要从报告页面重新下载。
