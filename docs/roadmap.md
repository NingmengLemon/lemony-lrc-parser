# Roadmap

只列未完成的条目。代号规则见 [docs/README.md](README.md#约定)。

## 0.5.x：收尾

| 代号 | 内容 |
| --- | --- |
| ARCH-1 | 合并逻辑拆到 `merge.py`，是 MERGE-1 的前置 |
| ARCH-2 | `models.py` 不再接收新实现，新功能落到独立模块 |
| TEST-1 | 引入 hypothesis 做性质测试 |

## 0.6.0：候选

按价值排序。

| 代号 | 内容 | 依赖 |
| --- | --- | --- |
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

### TEST-1：性质测试

解析器的边界情况多，适合用生成式测试兜底：

- `parse_timetag(format_timetag(ms))` 在精度允许的范围内还原。
- `loads(dumps(lyrics))` 语义等价。
- `apply_delta(a).apply_delta(b)` 等价于 `apply_delta(a + b)`。
- `combine` 不修改输入。

hypothesis 只进 dev 依赖。现有 `tests/test_roundtrip_matrix.py` 的固定种子
随机语料可以逐步迁过去。

### WRITE-1：保留原文件风格

真实语料里 100% 的文件写回后与原文件字节不同（[数据](research/corpus.md)）：
CRLF 变 LF，2 位尾数被补成 3 位，行间空行按 `line_separator` 重排。
解析没有问题，问题在"改写别人曲库"这个场景。

做法：

- `SerializationOptions` 增加 `line_ending`（`"lf"` / `"crlf"`）。
- 提供 `detect_style(text) -> DocumentStyle`，探测行尾、尾数位数、空行风格，
  可以直接转成 `SerializationOptions`。
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

现有 I/O 接收 `TextIO`。路径接口会牵扯 encoding、newline、覆盖策略，
最好与 WRITE-1 的行尾处理一起设计。

### EXPORT-1：ASS 导出

ASS 带样式、定位、特效，完整支持会超出本库定位。要做就只导出纯文本，不承诺
样式往返。届时 `subtitle.py` 再拆成包。
