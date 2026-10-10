# Roadmap

只列未完成的条目。代号规则见 [docs/README.md](README.md#约定)。

## 0.5.x：收尾

| 代号 | 内容 |
| --- | --- |
| ARCH-1 | 合并逻辑拆到 `merge.py`，是 MERGE-1 的前置 |
| ARCH-2 | `models.py` 不再接收新实现，新功能落到独立模块 |
| TEST-2 | 把 `test_roundtrip_matrix.py` 的固定种子随机语料迁到 hypothesis |

## 0.6.0：候选

按价值排序。

| 代号 | 内容 | 依赖 |
| --- | --- | --- |
| BREAK-1 | 移除 0.5.x 弃用的写法：`str in <模型>` 改为抛 `TypeError`，CLI 去掉 `--strict` | |
| WRITE-1 | 写回时保留原文件风格 | |
| MERGE-1 | 合并时按时间容差模糊匹配，并给出合并报告 | ARCH-1 |
| QUERY-1 | 按时间范围取行 | |
| META-1 | 读取 `[offset:]` 并显式应用的 helper | |
| PARSE-1 | 报告"非递减但差值过大"的行标签歧义 | |

## 有需求再做

| 代号 | 内容 |
| --- | --- |
| ANALYZE-1 | 统计信息 `LyricsStats` |
| ANALYZE-2 | 格式特征检测 `LyricsFeatures` |
| ANALYZE-3 | 两份歌词的差异比较，附 CLI 子命令 |
| EDIT-1 | 显式规范化 `normalize()` |
| PARSE-2 | 可选保留源位置 |
| PARSE-3 | `#` 开头的注释行 |
| PARSE-4 | 带小时的时间标签 `[hh:mm:ss.fff]` |
| PARSE-5 | 可选把空正文行保留为空行（默认仍读作结束标记） |
| QUERY-2 | 跨行正则搜索 |
| QUERY-3 | 搜索结果带行号 |
| MERGE-2 | 一次合并多份歌词 |
| META-2 | metadata 值的类型化读取 |
| META-3 | 可配置的 metadata key 规则 |
| IO-1 | 按路径读写 |
| EXPORT-1 | 导出 ASS |

## 观望

- Walaoke 对唱前缀（`M:` / `F:` / `D:`）：现实中很少见。
- `[#...]` 形式的 metadata 注释：`Metadata` 容器已经能装任意 key，门槛只在
  解析规则；没有明确需求前不放宽。
- warning 与 logging 的整体审计：不宜过度打扰用户。

---

## 条目详情

### ARCH-1：拆出 `merge.py`

`combine()` 现在很简单，但 MERGE-1 要加容差匹配、未匹配报告、模糊匹配审计，
它会变成一个合并引擎。先把现有逻辑原样搬进 `merge.py`：

```python
@dataclass(frozen=True)
class MergeOptions:
    other_as_refline_only: bool = True
    tolerance_ms: int = 0


@dataclass(frozen=True)
class MergeReport:
    exact_matches: int
    fuzzy_matches: int
    unmatched_main: tuple[int, ...]
    unmatched_other: tuple[int, ...]


def combine_lyrics(main, other, *, options: MergeOptions) -> Lyrics: ...
def combine_lyrics_with_report(
    main, other, *, options
) -> tuple[Lyrics, MergeReport]: ...
```

`Lyrics.combine()` 与 `+` 保留为默认策略的入口。这一步本身不改行为。

### ARCH-2：`models.py` 减重

`models.py` 约 1000 行。`Lyrics` 作为聚合入口是有意的（见
[architecture.md](design/architecture.md)），但入口方法只做委托，实现放进
各自的模块：合并进 `merge.py`，统计与特征进 `analysis.py`，规范化进
`normalize.py`，差异比较进 `diff.py`。

### TEST-2：随机语料迁到 hypothesis

`tests/test_roundtrip_matrix.py` 用固定种子的 `random` 生成 400 份语料，跑三条
往返不变量。`tests/test_properties.py` 已经用 hypothesis 覆盖了同样的不变量，
而且能自动缩小反例。迁完之后删掉 `_random_documents`，手写语料保留。

### BREAK-1：移除 0.5.x 的弃用项

- `str in LyricToken / BasicLyricLine / LyricLine / Lyrics` 抛 `TypeError`，
  提示改用 `contains_text()`。
- CLI `validate --strict` 删除，只留 `--fail-on-error`。

警告文本与 README 已经写明是 0.6.0。

### WRITE-1：保留原文件风格

真实语料里 100% 的文件写回后与原文件字节不同（[数据](research/corpus.md)）：
2 位尾数被补成 3 位，行间空行按 `line_separator` 重排，末尾换行统一补上。
解析没有问题，问题在"改写别人曲库"这个场景。行尾已经可以保留（探测后显式传
`line_ending`，见 [semantics.md](design/semantics.md#往返保真度)），剩下这几项。

做法沿用行尾的模式：只探测、不沿用，探测结果由调用方显式传回。

- 提供 `detect_style(text) -> DocumentStyle`，在 `detect_line_ending` 之外再探测
  尾数位数、空行风格、末尾有无换行，可以直接转成 `SerializationOptions`。
- 尾数位数按行或按词元探测，同一文件里 2 位与 3 位混用很常见。
- 显式参数始终可以覆盖探测结果。

### MERGE-1：模糊合并

翻译歌词的时间轴常与原文差几十到几百毫秒，按 `start` 精确匹配会漏。

匹配顺序：先精确匹配；剩下的 other 行在未匹配的主行里找
`abs(delta) <= tolerance_ms` 的最近一行；每个主行最多被模糊匹配一次。

风险：重复副歌、短句、rap 密集段落里，时间接近不代表内容对应。所以默认
`tolerance_ms=0`，结果必须可审计（`MergeReport`），CLI 的合并命令要输出
统计。`+` 运算符的行为不变。

### QUERY-1：时间范围查询

```python
def lines_in_range(
    self,
    start_ms: int,
    end_ms: int,
    *,
    mode: Literal["overlap", "contained", "start"] = "overlap",
) -> list[LyricLine]: ...
```

`overlap` 是与目标区间有交集，`contained` 是完全落在区间内，`start` 只看
`line.start`。要先定下来的是 `end is None` 的行怎么算：可以用下一行的
`start` 推断，也可以只按 `start` 判断。规模上直接遍历就够，不需要二分。

### META-1：offset helper

```python
def metadata_offset_ms(self) -> int | None: ...  # 解析失败返回 None
def apply_metadata_offset(self) -> Lyrics: ...  # 等价于 apply_delta(-offset)
```

LRC 的 `[offset: +N]` 是"歌词提前 N 毫秒"，而 `apply_delta(+N)` 是推后，
两者符号相反（[调研](research/offset.md)）。helper 的价值就是替用户把这个
负号写对。仍然不自动应用：有的播放器完全忽略 offset，要不要应用由调用方定。
符号约定已经有测试：`tests/test_offset.py::TestLrcOffsetConvention`。

### PARSE-1：行标签歧义提示

`[t1][t2]文本<...>` 在 t1、t2 非递减时读成"行标签 + 首字延迟"的一行
（[取舍](design/semantics.md#多个行首标签加逐字标记)）。语料里有 2 行两标签
相差 15 秒以上，按这个规则会被读成"首字延迟 15 秒"，实际更像重复行。

做法：差值超过阈值时发一个 `ParseEvent`（例如 `ambiguous-line-tags`），
不改变解析结果。是否进入 `STRICT_ERROR_CODES` 需要单独决定：它不是"丢掉了
声明"，按现有判据不该进。

### PARSE-5：保留空正文行

播放器生态多数把只有时间标签的行读成空行，在滚动列表里占一格
（[调研](research/blank-lines.md)）；本库读作结束标记。给需要前一种读法的消费方
一个选项，例如 `ParseOptions(keep_blank_lines=True)`，默认关闭。规则：

- 照常给上一行补 `end`，之后再决定要不要保留成一行。
- 与下一句同时间戳的空行只当结束标记，不产生行。
- 时间戳与上一个空行完全相同的去重（语料里 914 段连续空行的时间戳全相同）。
- 其余的保留为空正文行，不当锚点、不当宿主、不当参考行，与现有的尖括号空 cue
  一致。

要先定的：写回用尖括号（现有的空 cue 写法，能往返）还是方括号（读回时会再走结束
标记分支）；与 `fill_implicit_line_end`、字幕导出、`combine` 的交互。语料里能证明
需要它的写法很少（递增的连续空行基本是间奏里的空时间戳，不是挤出可视范围的表演
写法），有明确的消费方需求再做。

### ANALYZE-1 / ANALYZE-2：统计与特征

```python
@dataclass(frozen=True)
class LyricsStats:
    lines: int
    tokens: int
    references: int
    total_duration_ms: int | None
    has_byword: bool
    metadata_keys: tuple[str, ...]


@dataclass(frozen=True)
class LyricsFeatures:
    has_metadata: bool
    has_byword_tags: bool
    has_reference_lines: bool
    has_line_end_tags: bool
    has_folded_timestamps: bool
```

统计每次动态计算，不缓存，避免用户改了歌词后缓存失效。格式检测给 flags
而不是单一枚举：真实文件往往混合多种特征，"Simple / Enhanced / SPL" 的
单一分类不稳。ANALYZE-2 的探测逻辑与 WRITE-1 的 `detect_style` 可以共用。

### ANALYZE-3：差异比较

```python
def diff(self, other: Lyrics, *, tolerance_ms: int = 0) -> list[LyricsDiff]: ...
```

报告多出 / 缺失的行、文本差异、时间偏差、metadata 差异、参考行差异。
对调试往返和比较不同来源的歌词有用，CLI 对应 `diff a.lrc b.lrc`。

### EDIT-1：规范化

```python
def normalize(
    self,
    *,
    sort: bool = True,
    merge_duplicate_starts: bool = False,
    fill_implicit_line_end: bool = False,
    strip_empty_reference_lines: bool = True,
) -> Lyrics: ...
```

定位是用户主动调用，解析器本身不偷偷修数据。风险是它容易长成大杂烩，
选项要少，每个语义要单一。

### PARSE-2：源位置

```python
@dataclass(frozen=True)
class SourceLocation:
    line_no: int
    column: int | None = None
    raw_line: str | None = None
```

用 `ParseOptions(preserve_source_location=True)` 开启，存在 side table 里，
不塞进默认的 `LyricLine`。`LrcParser` 已经是它的挂载点。用途：`validate()`
定位到原文件行、CLI 错误信息、模糊合并的来源报告、QUERY-3。

### PARSE-3：注释行

部分实现允许 `#` 开头的注释行（[AMLL 文档](https://amll.dev/en/guides/lyric/formats)
提及）。现在这种行没有锚点时按孤儿行告警丢弃，有锚点时被挂成参考行，
两种都不对。倾向的做法是识别为注释、整行忽略、不告警，但要和孤儿行 /
参考行的规则一起定。

### PARSE-4：带小时的时间标签

社区整理把 `[hh:mm:ss.fff]` 列为在用写法，但本库读不了：尾数分隔符允许 `:`，
于是 `[01:02:03]` 读作 1 分 2.03 秒，`[01:02:03.500]` 整行被当成孤儿行
（[调研](research/timetags.md)）。语料里 0 例。

要支持就得在三段式标签上做选择：`[a:b:c]` 是"分:秒:百分秒"还是"时:分:秒"。
倾向的判据是"三段都齐全且末段带小数"才按小时读，`[a:b:c]` 维持现状，
但要先补一份语料统计看 `[mm:ss:xx]` 的实际用量。

### QUERY-2 / QUERY-3：搜索扩展

`find_regex` 是逐行匹配，`pattern` 里的 `\n` 永远匹配不到。跨行搜索要先
定义"跨几行、命中算哪一行"。结果带行号要等 PARSE-2，现在可以自己
`enumerate(lyrics)`。

### MERGE-2：批量合并

语义清楚，但链式 `combine` 已经能覆盖，等 ARCH-1 之后顺手做。

### META-2：类型化读取

`get_int(key)` / `get_float(key)` 一类的轻量 helper。不能借机自动应用
`offset`。

### META-3：可配置的 metadata key

默认规则（字母开头、最多 16 位字母数字）不变，`ParseOptions.meta_key_pattern`
允许传自定义正则。风险是 metadata 与正文里的 `[xxx:yyy]` 更容易混淆，要靠
"行首时间标签优先"的现有逻辑继续保护。`serializer.py` 写出时对不合规 key
的告警不预设这一条的结论。

### IO-1：路径读写

```python
Lyrics.from_path(path, encoding="utf-8-sig")
lyrics.to_path(path, encoding="utf-8")
```

现有 I/O 接收 `TextIO`。路径接口会牵扯 encoding、newline、覆盖策略。newline 的
答案已经有了：读写都用 `newline=""`，行尾交给 `line_ending`（与 CLI 一致）。

### EXPORT-1：ASS 导出

ASS 带样式、定位、特效，完整支持会超出本库定位。要做就只导出纯文本，不承诺
样式往返。届时 `subtitle.py` 再拆成包。
