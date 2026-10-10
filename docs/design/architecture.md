# 架构

## 模块分工

| 模块 | 职责 |
| --- | --- |
| `models.py` | 数据模型 `LyricToken` / `BasicLyricLine` / `LyricLine` / `Lyrics`，以及各种选项 dataclass |
| `metadata.py` | `Metadata`：有序、同名可重复的 ID 标签容器 |
| `parser.py` | LRC 文本 → `Lyrics`。公共入口 `parse_line` / `parse_lrc` / `parse_with_report`，内部是 `LrcParser` |
| `report.py` | 解析报告 `ParseReport` / `ParseEvent`，以及 strict 模式的触发集合 `STRICT_ERROR_CODES` |
| `serializer.py` | `Lyrics` → LRC 文本 |
| `validation.py` | 对结果数据做一致性检查，产出 `ValidationIssue` |
| `subtitle.py` | SRT / WebVTT 双向转换 |
| `offset.py` | 整体时间偏移 |
| `timetag.py` / `regex.py` | 时间标签的解析与格式化、正则常量，纯函数 |
| `cli.py` / `__main__.py` | `python -m lemony_lrc_parser`，只做参数、文件读写、输出和退出码 |
| `_utils.py` | 跨模块的内部小工具，不对外 |

依赖方向：`cli` 依赖核心库，核心库不感知 CLI；`validation` 只消费 `models`，
不依赖 parser 与 serializer。

## `Lyrics` 是聚合入口

`Lyrics` 继承 `UserList[LyricLine]`，同时承担面向对象的 API 入口：
`loads` / `dumps`、`validate`、`combine`、`apply_delta`、`to_srt` 等都在它身上。
这些方法通过函数级延迟导入委托给各自模块，`models.py` 只放入口，不放实现。

这是有意的取舍：用一个对象拿到全部高频操作，代价是 `Lyrics` 的方法面会变宽。
控制办法是只把高频、直觉上属于歌词对象的能力挂成方法，低频的工具型能力做成
独立模块的函数，顶层 `__all__` 保持克制。

`UserList` 意味着用户可以直接 `append` 乱序行或非预期对象，绕过不变量。
本库不重写所有 list mutator（成本高，也违反用户对 list 的预期），而是提供
`add_line` / `sort_inplace` / `sorted` 与 `validate()`，并在文档里写明直接 list
操作不排序、不校验。`lyrics.sort()` 不可用，因为 `LyricLine` 没有开 dataclass
的 `order`。

## 解析器

`parse_lrc` 是 `LrcParser` 的薄包装。解析状态（metadata、行池、参考行锚点、
结束标记的收尾目标、报告）挂在实例上，`parse()` 先 `reset()`，所以实例可复用；
`parse_raw_line()` 支持逐行喂入，此时重置由调用方负责。`LrcParser` 不在
`__all__` 里，属于内部对象。

`parse_line()` 内部发生的事件以 `ParseEvent` 的形式通过 `on_event` 回调交给
`LrcParser`。`parse_line()` 不知道源文件行号，所以事件的 `line_no` /
`raw_line` 为空，由 `LrcParser` 用 `dataclasses.replace` 补上再写进报告。
回调收对象而不是拆开的字段，以后给事件加字段不会破坏回调签名。

## 报告、校验与 strict 的关系

三者覆盖不同阶段，共用一套 kebab-case 代码命名：

- `ParseReport` 是事后审计：解析过程中丢了什么、忽略了什么、改了什么。干净
  文件的报告为空，正常操作只进计数。
- `ParseOptions(strict=True)` 是当场拒绝：报告里属于 `STRICT_ERROR_CODES`
  的事件直接抛 `InvalidLyricsError`。事件先入报告再抛，接住异常后仍能读到
  已累积的报告。
- `validate()` 检查结果数据本身，不关心它是解析来的还是手工构造的。

strict 的判据只有一句：解析器不得不丢掉或忽略文件里的某个声明。
`line-filtered` 不触发（那是调用方要求丢的）；metadata key 不合法、`offset`
不可解析也不触发（不影响解析结果，归 `validate()`）。

CLI 的 `validate` 把前后两者都输出：先是解析报告（位置是源文件行号），再是
校验问题（位置是解析后的行下标）。`STRICT_ERROR_CODES` 里的事件和 error 级
校验问题都算 error，`--fail-on-error` 据此决定退出码。它只管退出码，不改解析
行为，所以没有沿用 "strict" 这个词。`validate` 期间在库的 logger 上挂一个
`NullHandler`，避免同一批 warning 经 Python 的 last-resort handler 再打一遍；
调用方自己配置的 handler 不受影响。

## 演进方向

- 有状态、策略、报告需求的功能做成独立模块：合并（`merge.py`，见 roadmap
  ARCH-1）、统计与特征（`analysis.py`）、规范化、差异比较。
- 纯转换不硬拆：`timetag.py` / `regex.py` 保持纯函数；`subtitle.py` 在出现
  第三种字幕格式之前不拆成包。
- 版本还在 0.x，内部边界整理趁现在做，避免稳定版之后再破坏兼容。
