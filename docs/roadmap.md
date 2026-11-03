# Roadmap

只列未完成的条目。代号规则见 [docs/README.md](README.md#约定)。

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
