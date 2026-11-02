# Roadmap

只列未完成的条目。代号规则见 [docs/README.md](README.md#约定)。

输出以固定、可复现的规范写法为准，不做源风格对齐；SPL 只作参照。

## 现在（非破坏性）

| 代号 | 内容 |
| --- | --- |
| TEST-2 | `test_roundtrip_matrix.py` 的固定种子随机语料迁到 hypothesis |
| DOC-1 | 新增语料统计与可复跑脚本；记录采集日期和处理步骤；旧统计标为历史快照 |
| DOC-2 | 写清输出规范与行级往返契约；修正 README 的往返检查表述与 `Lyrics.__eq__` 的 docstring |
| QUERY-1 | 新增 `query.py`，收拢 `contains_text` / `find_text` / `find_regex` / `contains_regex` 并加 `lines_in_range(start_ms, end_ms)`；只做交集，`end is None` 的行按下一行 `start` 推断，最后一行延伸到区间终点 |
| MERGE-1 | 精确匹配后按毫秒级容差找最近行，附合并报告；同时拆出 `merge.py` |

## 0.6.0（暂缓，等主要使用方完成升级准备）

| 代号 | 内容 |
| --- | --- |
| BREAK-1 | 移除当前弃用项：`str in <模型>` 抛 TypeError，CLI 去掉 `--strict` |
| BREAK-2 | 移除 `+` / `+=`：覆盖为 `NotImplemented`，阻止回落到 `UserList` 的列表拼接；0.5.x 已弃用 |

## 有明确需求再做

| 代号 | 内容 |
| --- | --- |
| META-1 | `[offset:]` helper |
| PARSE-3 | `#` 注释行；先定和孤儿行、参考行的交互 |
| PARSE-4 | 带小时的时间标签；先拿到真实文件并定消歧规则 |
| PARSE-5 | 可选保留空正文行 |
| ANALYZE-1 / 2 | 统计 / 特征 |
| META-2 | 类型化读取 |
