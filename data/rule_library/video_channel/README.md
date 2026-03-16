# 视频号规则库

已完成基于视频号官方页面《微信视频号运营规范》与《视频号常见违规内容概览》的本地化。

当前文件：

- `catalog.json`
- `rules.json`
- `../../source_archives/video_channel_video_guide/full_archive_20260316/`
- `../../source_archives/video_channel_operation_standards/full_archive_20260316/`

特点：

- 合并两份官方页后共 `394` 条规则
- `VC-*` 来自《视频号常见违规内容概览》
- `VC-STD-*` 来自《微信视频号运营规范》
- 将违规概览页的官方案例图片本地化到规则条款下
- 保留案例视频链接到规则元数据中
- 生成了可离线查看的 [`index_local.html`](../../source_archives/video_channel_video_guide/full_archive_20260316/index_local.html)
- 生成了运营规范离线归档 [`index_local.html`](../../source_archives/video_channel_operation_standards/full_archive_20260316/index_local.html)

如需重新生成：

```bash
python scripts/build_video_channel_rule_library.py
```
