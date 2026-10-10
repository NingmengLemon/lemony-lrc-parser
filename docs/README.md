# 开发文档

面向维护者与贡献者。使用说明见仓库根目录的 [README](../README.md)，
版本变更见 [CHANGELOG](../CHANGELOG.md)。

| 文档 | 回答的问题 |
| --- | --- |
| [roadmap.md](roadmap.md) | 接下来做什么，按什么顺序 |
| [design/architecture.md](design/architecture.md) | 模块怎么分工，往哪个方向演进 |
| [design/semantics.md](design/semantics.md) | 解析与序列化的语义取舍，以及为什么 |
| [design/not-planned.md](design/not-planned.md) | 明确不做的事和理由 |
| [research/](research/) | 调研与语料数据，所有取舍的证据 |

research 目录下按主题分文件：

- [corpus.md](research/corpus.md)：真实语料基线。
- [spl.md](research/spl.md)：与 SPL 标准的逐条对照。
- [blank-lines.md](research/blank-lines.md)：空正文行在各家实现里的读法与语料统计。
- [metadata.md](research/metadata.md)：ID 标签、value 里的方括号、同名 key 的容器。
- [offset.md](research/offset.md)：`[offset:]` 的正负语义。
- [timetags.md](research/timetags.md)：时间标签的宽松写法。
- [typing-extensions.md](research/typing-extensions.md)：依赖下限实测。

## 约定

- 文档只描述现状。某个功能怎么一步步变成现在这样，属于 CHANGELOG 和
  `git log`。
- roadmap 只放未完成的条目。条目落地后从 roadmap 删除，写进 CHANGELOG；
  如果它带来了值得长期记住的取舍，写进 `design/`。
- 条目代号形如 `WRITE-1`：前缀是主题，序号在主题内递增，不复用。代码注释
  可以引用未完成条目的代号，条目落地时要一并改成描述性文字（用
  `rg '\b[A-Z]+-[0-9]+\b' src tests` 检查）。
- 调研结论一律带出处。LRC 没有官方规范，很多"常识"其实只是某个实现的
  行为，见下一节。

## 为什么要这么多调研

LRC 是从 Winamp 时代的播放器行为里长出来的格式，从来没有官方规范。
Wikipedia、各家播放器文档、事实参考实现（ffmpeg）之间互相矛盾：

- `offset` 的正负：社区文档说正值让歌词提前，KDE Elisa 曾经反着实现并
  被单独修过。
- metadata 的 value 能不能含 `]`：ffmpeg 取第一个 `]` 收尾，真实用户文件里
  却有 `[ti: Song [Explicit]]` 这种写法。
- 转义语法根本不存在，谁引入谁就在造方言。

唯一像样的书面参照是 [SPL](https://moriafly.com/standards/spl.html)，
本库按它逐条对照过，结果见 [research/spl.md](research/spl.md)。

因此本库的总策略是：默认宽松解析，不确定的地方告警而不是猜，每个判断的
依据与代价写进 [design/semantics.md](design/semantics.md)。
