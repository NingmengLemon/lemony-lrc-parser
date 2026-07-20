# Feature Ideas for lemony-lrc-parser

本文档用于跟踪 `lemony-lrc-parser` 的后续功能、设计改进、风险与暂不计划事项。

> 背景判断：项目目前已经具备稳定的 LRC 解析 / 序列化核心、逐字标签支持、参考行模型、时间偏移、字典序列化、SRT / WebVTT 互转与较完整的测试。后续更适合优先补“开发者体验、可诊断性、数据一致性、CLI 工具化”，而不是盲目扩展冷门 LRC 方言。

---

## 目录

- [当前项目概况](#当前项目概况)
- [优先级路线图](#优先级路线图)
- [模块立体化 / 大胆重构方向](#模块立体化--大胆重构方向)
- [候选功能与设计改进](#候选功能与设计改进)
- [我的新增想法](#我的新增想法)
- [可能的问题与风险](#可能的问题与风险)
- [已完成](#已完成)
- [已关闭 / 不计划](#已关闭--不计划)
- [极低优先级 / 观望](#极低优先级--观望)

---

## 当前项目概况

### 已有能力

- 标准 LRC 解析与序列化。
- Enhanced LRC / SPL 风格逐字时间标签解析。
- metadata 标签解析。
- 折叠时间标签展开。
- 参考行支持，用于翻译、音译等辅助文本。
- 歌词合并，并将同时间点的另一份歌词挂为参考行。
- 时间偏移与运算符形式的整体前移 / 后移。
- 数据模型 `to_dict()` / `from_dict()` 往返。
- SRT / WebVTT 双向转换。
- 文件对象 I/O 入口。
- 类型注解与 `py.typed`。

### 当前设计取舍

- `Lyrics` 是基于 `UserList[LyricLine]` 的容器，同时承担聚合 API 入口职责。
- `LyricLine.start` 已经收敛为必需的 `int`，无时间戳行目前不会进入正常行模型。
- 解析器默认偏宽松：部分异常格式会被跳过或记录 warning，而不是直接失败。
- 内部时间精度是毫秒；输出为百分秒或其他尾数长度时可能有损。
- subtitle 互转会丢弃逐字标签与 metadata，这是格式差异导致的预期行为。

---

## 优先级路线图

### P0 / 高优先级：建议优先做

| ID | 主题 | 类型 | 价值 | 备注 |
| --- | --- | --- | --- | --- |
| F-VALIDATE | 数据一致性验证 API | 质量 / DX | 高 | 后续 strict mode、CLI validate、CI 校验都可复用 |
| NEW-ERROR-LINE | 解析错误包含行号与原始行 | 可诊断性 | 高 | 多行 LRC 调试时收益很大 |
| NEW-CLI | CLI 入口 | 工具化 | 高 | 可让非库用户直接验证、偏移、转换、合并歌词 |
| B7 | 逐字时间戳与行时间范围一致性校验 | 正确性 | 高 | 可合并进 `validate()`，默认不破坏宽松解析 |
| NEW-ROUNDTRIP | Roundtrip Fidelity 测试矩阵 | 回归保障 | 高 | 对解析 / 序列化库非常关键 |

### P1 / 中优先级：稳定核心后推进

| ID | 主题 | 类型 | 价值 | 备注 |
| --- | --- | --- | --- | --- |
| F-STRICT | 解析严格模式 | 可控性 | 中高 | 最好建立在 `validate()` 与行号错误之上 |
| F-RANGE | 时间范围查询 | API | 中 | 对播放器、剪辑、字幕片段提取有用 |
| F-MUTATE | 安全变更方法 | API | 中 | 降低用户直接操作 list 破坏排序的概率 |
| NEW-SEARCH | 全文搜索 | API | 中 | 实现简单，使用频率可能不低 |
| MF-FUZZY | 合并歌词时模糊匹配 | 实用增强 | 中 | 翻译歌词时间轴常有轻微偏差 |
| F-DICT-JSON | JSON 便捷序列化 | DX | 中 | 建议保持薄封装，避免复杂自定义编码器 |
| F-REPR | 自定义紧凑 repr | DX | 中 | 调试体验改善明显 |

### P2 / 低优先级：有需求再做

| ID | 主题 | 类型 | 价值 | 备注 |
| --- | --- | --- | --- | --- |
| F-DURATION | `LyricLine.duration` 属性 | API | 低中 | 简单但要定义 `end is None` 的语义 |
| F-CONTAINS | `Lyrics.__contains__` 增强 | API | 低中 | 行搜索语义可能与 `search()` 重叠 |
| F-COMBINE-ALL | 批量合并 | API | 低 | 语义清晰但链式合并已可覆盖 |
| NEW-STATS | `Lyrics.stats` | 信息辅助 | 低中 | 可基于 `validate()` / 格式检测共同实现 |
| NEW-DETECT | LRC 格式自动检测 | 信息辅助 | 低 | “SPL 是否单独算格式”需要谨慎 |
| F-META-TYPE | metadata 值类型辅助 | API | 低 | 可做成轻量 helper |
| F-META-KEY | metadata key 可配置 | 兼容性 | 低 | 可能扩大歧义 |
| F-EXPORT-OTHER | ASS 等其他字幕格式导出 | 格式扩展 | 低 | ASS 支持复杂样式，可能超出当前库定位 |
| F-LOGGING | warning / logging 审计 | 体验 | 低 | 不宜过度打扰用户 |

---

## 模块立体化 / 大胆重构方向

> 当前版本仍处于 `0.x.y` 且是 beta 阶段，可以接受更大胆的内部重构；目标不是为了“架构感”而拆模块，而是趁 API 兼容负担较轻时，把已经显露出状态、策略、报告、诊断需求的模块变得更“立体”。

### 总体原则

- 对外 API 尽量保持稳定，内部实现可以大胆拆分。
- 高频、直觉上属于歌词对象自身的入口仍可保留在 `Lyrics` 上，但具体实现尽量下沉到专门模块。
- 有“状态 / 策略 / 报告 / 诊断信息”的功能适合立体化；纯转换、纯格式化工具不必硬拆。
- 趁 beta 阶段优先完成内部边界整理，避免未来稳定版后再做破坏性调整。

### A1：解析器从平铺函数升级为有上下文的 `LrcParser`

当前 `parse_lrc()` 内部已经承载了多种解析状态：metadata、行池、参考行锚点、warning 策略、歧义处理等。随着 strict mode、行号错误、source map、unsynced line 收集等功能加入，继续平摊在单个函数里会越来越难维护。

建议引入内部解析器对象：

```python
class LrcParser:
    def __init__(self, options: ParseOptions): ...
    def parse(self, text: str) -> Lyrics: ...
    def parse_raw_line(self, line_no: int, raw_line: str) -> None: ...
    def finalize(self) -> Lyrics: ...
```

对外仍保留原入口：

```python
def parse_lrc(lrc: str, *, options: ParseOptions | None = None) -> Lyrics:
    return LrcParser(options or ParseOptions()).parse(lrc)
```

收益：

- 行号、原始行、source map 有明确承载位置。
- strict / warning / 宽松解析策略可以统一收口。
- 解析状态不再散落在局部变量与 helper 之间。
- 更容易测试单行处理、metadata 处理、reference line 锚定等内部步骤。

### A2：新增 `validation.py`，让验证成为独立子系统

`validate()` 是 strict mode、CLI validate、roundtrip 测试、模糊合并审计的共同地基，不适合继续塞进 `models.py`。

建议新增：

```text
src/lemony_lrc_parser/validation.py
```

核心结构：

```python
@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: Literal["warning", "error"]
    line_index: int | None = None
    token_index: int | None = None


def validate_lyrics(lyrics: Lyrics, *, options: ValidationOptions | None = None) -> list[ValidationIssue]: ...
```

`Lyrics.validate()` 只做薄委托，避免 `models.py` 继续膨胀。

### A3：把合并逻辑从 `Lyrics` 拆到 `merge.py`

当前 `combine()` 还简单，但模糊匹配、批量合并、未匹配报告、matched-by-fuzzy 审计都会让它变成“合并引擎”，而不只是一个容器方法。

建议新增：

```text
src/lemony_lrc_parser/merge.py
```

可能结构：

```python
@dataclass(frozen=True)
class MergeOptions:
    other_as_refline_only: bool = True
    tolerance_ms: int = 0
    keep_unmatched: bool = False

@dataclass(frozen=True)
class MergeReport:
    exact_matches: int
    fuzzy_matches: int
    unmatched_main: tuple[int, ...]
    unmatched_other: tuple[int, ...]


def combine_lyrics(main: Lyrics, other: Lyrics | Iterable[LyricLine], *, options: MergeOptions) -> Lyrics: ...
def combine_lyrics_with_report(...) -> tuple[Lyrics, MergeReport]: ...
```

`Lyrics.combine()` 与 `+` 运算符继续保留为默认策略的便捷入口。

### A4：`models.py` 保持 facade，但不要继续当 implementation sink

`Lyrics` 作为聚合层是有意取舍，可以继续保留高频入口，但应避免把所有实现都塞进 `models.py`。

建议保留在 `Lyrics` 上的薄入口：

- `loads()` / `dumps()` / `load()` / `dump()`。
- `copy()`。
- `apply_delta()`。
- `to_srt()` / `to_webvtt()` / `from_srt()` / `from_webvtt()`。
- 简单高频 API，如 `search()` 或 `duration`。

建议下沉到专门模块的实现：

- 验证：`validation.py`。
- 合并策略：`merge.py`。
- 统计与格式特征：`analysis.py` 或 `features.py`。
- 规范化：`normalize.py`。
- 差异比较：`diff.py`。
- CLI：`cli.py` / `__main__.py`。

### A5：CLI 作为应用层独立存在

若实现命令行入口，应新增：

```text
src/lemony_lrc_parser/cli.py
src/lemony_lrc_parser/__main__.py
```

CLI 只负责参数解析、文件读写、stdout / stderr、退出码，并调用核心库能力；核心库不应反向感知 CLI。

### A6：`subtitle.py` 暂缓拆分，等复杂格式出现再升级

当前 SRT / WebVTT 互转还是纯转换逻辑，平铺函数足够清晰。若未来支持 ASS 或更多字幕格式，可再拆为：

```text
src/lemony_lrc_parser/subtitle/
    __init__.py
    common.py
    srt.py
    webvtt.py
    ass.py
```

不建议现在为了“结构感”过早拆分。

### A7：`timetag.py` / `regex.py` 继续保持纯函数模块

时间标签解析、格式化和正则生成是典型纯函数工具。除非未来出现复杂 profile、rounding policy、format strategy，否则不建议引入类或过度分层。

### 建议重构顺序

1. 新增 `validation.py`，实现结构化验证结果。
2. 将 `parser.py` 内部改成 `LrcParser` 上下文对象，对外 API 不变。
3. 新增 `cli.py` / `__main__.py`，优先实现 validate、offset、to-srt、to-webvtt。
4. 新增 `merge.py`，把现有 combine 逻辑迁移过去，再实现 fuzzy merge 与 report。
5. 按需求新增 `analysis.py` / `features.py` / `normalize.py` / `diff.py`。

---

## 候选功能与设计改进

### F-VALIDATE：数据一致性验证 API

建议新增 `Lyrics.validate()`，集中检查数据模型的内部一致性。

建议检查项：

- 歌词行是否按 `start` 升序排列。
- 是否存在重复 `start`。
- 是否存在 `end <= start`。
- 逐字 token 的 `start` / `end` 是否单调。
- 逐字 token 是否落在所属行的 `[line.start, line.end]` 范围内。
- reference line 内部 token 时间是否合理。
- metadata key 是否符合当前 parser 支持的格式。
- `metadata.offset` 是否可解析为整数。

建议返回结构：

```python
@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: Literal["warning", "error"]
    line_index: int | None = None
    token_index: int | None = None


def validate(self, *, strict: bool = False) -> list[ValidationIssue]: ...
```

设计建议：

- 默认只返回问题列表，不抛异常。
- `strict=True` 时遇到 error 级别问题可抛出统一异常。
- CLI 的 `validate` 命令直接复用这套能力。

### NEW-ERROR-LINE：解析错误包含行号与原始行

当前多行 LRC 出错时，异常只说明“发生了什么”，不容易定位“发生在哪一行”。建议解析循环改为保留行号与原始内容。

建议形式：

```python
raise InvalidLyricsError(
    f"Line {line_no}: unexpected sequence length: {len(sequence)}; raw={raw_line!r}"
)
```

注意点：

- `lrc.strip().splitlines()` 会改变原始首尾空行的行号语义；若要保留准确行号，应考虑直接 `lrc.splitlines()`。
- 对宽松模式下的 warning，也建议带行号。
- 若未来引入结构化异常，可加 `line_no`、`raw_line` 属性，而不只是拼消息。

### NEW-CLI：命令行入口

建议新增 `python -m lemony_lrc_parser` 或 console script。

优先命令：

```bash
python -m lemony_lrc_parser validate song.lrc
python -m lemony_lrc_parser offset song.lrc --delta 500 -o song.offset.lrc
python -m lemony_lrc_parser combine main.lrc trans.lrc -o combined.lrc
python -m lemony_lrc_parser to-srt song.lrc -o song.srt
python -m lemony_lrc_parser to-webvtt song.lrc -o song.vtt
```

建议先做最小 CLI：

1. `validate`
2. `offset`
3. `to-srt`
4. `to-webvtt`

`combine` 可以第二阶段做，因为合并策略、模糊匹配、未匹配行输出都需要更多设计。

### B7：逐字时间戳与行时间范围一致性校验

问题：当前解析后可能出现 token 时间与所属行时间范围不一致的数据，例如：

- `word.start < line.start`
- `word.end > line.end`
- `word.end <= word.start`
- token 时间不单调

建议不要直接在宽松解析阶段抛异常，否则可能破坏对野生 LRC 的兼容性。更好的方式：

- 在 `validate()` 中报告。
- 在 `ParseOptions.strict=True` 时升级为异常。
- 在 `SerializationOptions` 中可选启用“序列化前校验”。

### NEW-ROUNDTRIP：轮转一致性测试矩阵

目标：确保 `loads(dumps(lyrics))` 在语义上尽量等价于原始对象。

建议覆盖：

- 普通 LRC。
- 折叠时间标签。
- 逐字 LRC。
- 参考行。
- metadata。
- 行尾时间标签。
- `line_separator` 不同配置。
- `tail_digits=2` 的有损场景明确标记为 expected lossy。

注意：metadata 字典顺序在现代 Python 中可保持插入顺序，但不应把“文本完全一致”作为唯一目标；建议区分：

- text roundtrip：字符串完全一致。
- semantic roundtrip：模型语义一致。

### F-STRICT：解析严格模式

建议在 `ParseOptions` 增加 `strict: bool = False`。

严格模式可将以下情况从 warning / 忽略升级为异常：

- 孤立无时间戳行。
- 非单调逐字时间标签。
- 行首重复时间标签与逐字标签组合造成歧义。
- metadata key 不合法。
- 重复且冲突的 metadata。
- 不可解析的 `offset` metadata。

设计建议：

- strict mode 不应改变数据模型，只改变错误处理策略。
- strict mode 最好与结构化 `ValidationIssue` 共用错误代码。
- README 中应明确默认宽松，以兼容真实世界的 LRC。

### F-RANGE：时间范围查询

建议新增：

```python
def lines_in_range(
    self,
    start_ms: int,
    end_ms: int,
    *,
    mode: Literal["overlap", "contained", "start"] = "overlap",
) -> list[LyricLine]: ...
```

语义：

- `overlap`：行时间区间与目标区间有交集。
- `contained`：行完全落在目标区间内。
- `start`：只看 `line.start` 是否在范围内。

注意点：

- `line.end is None` 时如何判断 overlap 需要定义，可用下一行开始时间推断，也可只按 `start` 处理。
- 如果列表始终有序，未来可考虑二分优化；当前规模下直接遍历足够。

### F-MUTATE：安全变更方法

`Lyrics` 继承自 `UserList`，用户可以直接 `append` / `insert` / `__setitem__`，这会绕过排序与验证。

建议新增轻量方法：

```python
def add_line(self, line: LyricLine, *, sort: bool = True) -> None: ...
def sorted(self) -> Lyrics: ...
def sort_inplace(self) -> None: ...
```

不建议强行禁止 list 操作，否则会破坏 `UserList` 的直觉。文档中说明：需要保持时间顺序时优先使用安全方法。

### MF-FUZZY：合并歌词时模糊匹配

现实中翻译歌词经常与原文存在几十到几百毫秒偏差，完全按 `start` 匹配会漏合并。

建议 API：

```python
def combine(
    self,
    other: Lyrics | Iterable[LyricLine],
    *,
    other_as_refline_only: bool = True,
    tolerance_ms: int = 0,
) -> Lyrics: ...
```

匹配策略：

1. 先做精确 `start` 匹配。
2. 对未匹配的 other 行，在未匹配主行中寻找 `abs(start_delta) <= tolerance_ms` 的最近行。
3. 同一主行只能被模糊匹配一次，避免多行挤到同一时间点。

风险：

- 重复副歌、短间隔歌词容易误匹配。
- 需要返回或暴露未匹配行信息，否则用户很难检查结果。

建议先做独立方法或选项，不改变现有 `+` 运算符默认行为。

### NEW-SEARCH：全文搜索

建议新增：

```python
def search(
    self,
    text: str,
    *,
    include_reference_lines: bool = True,
    case_sensitive: bool = True,
) -> list[LyricLine]: ...
```

实现简单，用户价值明确。若后续支持正则，可再加 `search_regex()`，不要让一个方法参数过多。

### F-DICT-JSON：JSON 便捷序列化

当前已有 `to_dict()` / `from_dict()`，可增加薄封装：

```python
def to_json(self, **json_kwargs: Any) -> str: ...
@classmethod
def from_json(cls, s: str) -> Lyrics: ...
```

建议：

- 默认 `ensure_ascii=False`，更适合歌词文本。
- 不要引入额外依赖。
- 文档中说明 JSON schema 不承诺永久稳定，除非打算正式支持外部存储格式。

### F-REPR：自定义紧凑 repr

当前默认 repr 对嵌套歌词较冗长。建议：

```python
LyricToken('hello', start=1000, end=1500)
LyricLine(start=1000, end=3000, text='hello...', refs=1)
Lyrics(lines=42, metadata={'ti': '...', 'ar': '...'})
```

注意：repr 应用于调试，不应追求可 `eval()`。

### F-DURATION：`LyricLine.duration` 属性

建议实现：

```python
@property
def duration(self) -> int | None:
    return None if self.end is None else self.end - self.start
```

由于 `start` 已经不允许为 `None`，无需再检查。

### F-CONTAINS：`Lyrics.__contains__` 增强

当前 `LyricToken` 与 `BasicLyricLine` 已支持字符串子串搜索。`Lyrics.__contains__` 可以扩展为：

- `LyricLine in lyrics`：保持 list 原语义。
- `"text" in lyrics`：搜索主行与参考行文本。

但这会让 `in` 的语义变宽，可能不如显式 `lyrics.search("text")` 清晰。建议若实现，也只作为 `search()` 的便捷语法。

### NEW-STATS：统计信息属性

可新增 `LyricsStats`：

```python
@dataclass(frozen=True)
class LyricsStats:
    lines: int
    tokens: int
    references: int
    total_duration_ms: int | None
    avg_line_duration_ms: float | None
    has_byword: bool
    has_reference_lines: bool
    metadata_keys: tuple[str, ...]
```

建议先实现为 property 动态计算，不缓存，避免用户修改歌词后缓存失效。

### NEW-DETECT：LRC 格式自动检测

建议谨慎处理，不要过度分类。

更实用的检测结果可能是 flags，而不是单一 enum：

```python
@dataclass(frozen=True)
class LyricsFeatures:
    has_metadata: bool
    has_byword_tags: bool
    has_reference_lines: bool
    has_line_end_tags: bool
    has_folded_timestamps: bool
```

原因：真实 LRC 往往是混合特征，“Simple / Enhanced / SPL” 单一分类并不稳。

### F-META-TYPE：metadata 值类型辅助

建议轻量实现：

```python
def get_metadata_int(self, key: str, default: int | None = None) -> int | None: ...
def get_metadata_float(self, key: str, default: float | None = None) -> float | None: ...
```

注意不要自动应用 `offset`，保持显式原则。

### F-META-KEY：metadata key 更宽松 / 可配置

当前 metadata key 限制较保守。可选方案：

- 保持默认不变。
- `ParseOptions.meta_key_pattern` 允许用户传入自定义正则。
- strict mode 下继续使用默认规范。

风险：metadata 与歌词正文中的 `[xxx:yyy]` 更容易误判，需要配合“行首时间标签优先”的现有逻辑继续保护。

---

## 我的新增想法

### MY-SOURCE-MAP：保留源位置信息（可选）

为调试和 CLI 输出考虑，可选保留每行来源：

```python
@dataclass(frozen=True)
class SourceLocation:
    line_no: int
    column: int | None = None
    raw_line: str | None = None
```

不建议直接塞进默认 `LyricLine`，避免污染轻量模型。可以通过 `ParseOptions(preserve_source_location=True)` 开启，并存到 side table 或扩展字段。

价值：

- `validate()` 输出可定位到原文件行。
- CLI 可以打印更友好的错误。
- 模糊合并后可报告来源。

### MY-NORMALIZE：规范化 API

新增显式规范化方法：

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

定位：不在 parser 中偷偷修数据，而是用户主动调用。

可做的事：

- 排序。
- 删除空参考行。
- 合并重复时间点。
- 补行尾时间。
- 清理空 token。

风险：normalize 容易变成“大杂烩”，必须保持选项少且语义明确。

### MY-DIFF：歌词差异比较工具

对调试 roundtrip、比较不同来源歌词很有用：

```python
def diff(self, other: Lyrics, *, tolerance_ms: int = 0) -> list[LyricsDiff]: ...
```

可报告：

- 多出的行 / 缺失的行。
- 文本不同。
- 时间偏差。
- metadata 差异。
- reference line 差异。

这也能服务测试与 CLI：`python -m lemony_lrc_parser diff a.lrc b.lrc`。

### MY-OFFSET-METADATA-HELPER：读取但不自动应用 offset

不建议 `apply_delta()` 自动清理 metadata.offset，但可以提供显式 helper：

```python
def metadata_offset_ms(self) -> int | None: ...
def apply_metadata_offset(self) -> Lyrics: ...
```

这样既保持“显式优于隐式”，又降低用户自己解析 `[offset:...]` 的重复成本。

### MY-ENCODING-HELPER：面向文件路径的便利读取

当前文件 I/O 接收 `TextIO`，这很 Pythonic。CLI 或普通用户可能更想要：

```python
Lyrics.from_path(path, encoding="utf-8-sig")
lyrics.to_path(path, encoding="utf-8")
```

建议低优先级，因为路径 I/O 会引入 encoding、newline、覆盖策略等额外决策；但对 CLI 内部实现有帮助。

### MY-PROPERTY-BASED-TESTS：性质测试

解析器涉及大量边界情况，建议引入 property-based tests（如生成合法时间戳、随机 token、随机 metadata）：

- `parse_timetag(format_timetag(ms))` 在精度允许范围内成立。
- `loads(dumps(lyrics))` 语义等价。
- `apply_delta(a).apply_delta(b)` 等价于 `apply_delta(a+b)`。
- `combine` 不修改输入对象。

这类测试特别适合防止未来重构破坏边界行为。

---

## 可能的问题与风险

### 1. LRC 缺少统一标准，严格模式容易误伤真实文件

LRC 野生格式很多。过早把 parser 默认行为改严，会破坏兼容性。

建议：

- 默认继续宽松。
- `strict=True` 明确 opt-in。
- 宽松解析 + `validate()` 报告问题，是更稳的路线。

### 2. `Lyrics` 继承 `UserList`，用户可绕过不变量

例如用户可直接插入乱序行，或把非预期对象放进列表。

建议：

- 文档说明“直接 list 操作不会自动 validate / sort”。
- 提供 `add_line()` / `sort_inplace()` / `validate()`。
- 不建议强行重写所有 list mutator，成本高且容易违反用户预期。

### 3. 行尾时间语义不稳定

LRC 行尾标签可选，SRT / WebVTT 必须有 end。这会导致导出字幕时需要推断。

建议：

- `SubtitleOptions` 当前方向正确。
- `duration`、`lines_in_range`、`stats` 都必须明确 `end is None` 的处理策略。

### 4. 逐字标签与行标签组合存在歧义

连续行首时间标签 + 行内逐字标签时，可能既像折叠行，又像空 token 的逐字行。

建议：

- 保持当前保守处理。
- strict mode 下把歧义作为 error。
- 文档中补充该行为说明。

### 5. metadata 是 `dict[str, str]`，无法表达重复 tag 与注释 tag

如多个 `[#...]` 注释或重复 `[ar:...]`，dict 会覆盖旧值。

建议：

- 暂时不要为了冷门方言破坏简单模型。
- 如确有需求，可未来增加 `metadata_items: list[tuple[str, str]]` 或 source map，但这属于较大模型变更。

### 6. JSON schema 一旦公开可能形成兼容负担

`to_dict()` 已经存在，若增加 `to_json()`，用户可能把它当稳定存储格式。

建议：

- 文档标注“用于传输 / 调试，非长期稳定文件格式”，除非项目决定正式版本化 schema。
- 若要长期稳定，应添加 `schema_version`。

### 7. 模糊合并可能产生错误关联

时间接近不代表歌词对应，尤其在重复副歌、短句、rap 密集歌词中。

建议：

- 默认 `tolerance_ms=0`。
- 模糊匹配结果最好可审计：返回 unmatched / matched-by-fuzzy 信息。
- CLI combine 中应输出统计。

### 8. CLI 会扩大维护面

CLI 涉及参数设计、路径、编码、退出码、错误输出、Windows shell 兼容等问题。

建议：

- 第一阶段只做少量命令。
- CLI 尽量薄封装核心库能力。
- 为退出码写测试。

### 9. ASS / 高级字幕格式可能偏离项目定位

ASS 支持样式、定位、特效，完整支持会显著扩大复杂度。

建议：

- 如要做，先只支持纯文本导出。
- 不承诺样式往返。
- 低优先级。

### 10. 过多便利 API 可能让核心模型变胖

`Lyrics` 已经是聚合层，继续增加 stats、search、normalize、diff、path I/O 等方法会让类变大。

建议：

- 高频能力放 `Lyrics` 方法。
- 低频 / 工具型能力可放独立模块函数。
- 保持顶层公共 API 有节制。

---

## 已完成

### v0.3.x

- **[B1] 仅含逐字标签的行被误判为参考行**

  修复：解析时若行首没有方括号时间标签，但解析出的第一个 token 有 `start`，则以该时间作为行开始时间。

- **[B3] 参考行格式化时错误传入主行的 `line_end`**

  修复：序列化参考行时使用 `line_end=None`，避免错误省略参考行最后一个词元的结束标签。

- **[B4] `parse_timetag` 与解析器宽松行为不一致**

  修复：统一使用更宽松的行时间标签正则。

### v0.4.x

- **[B5] `LyricLine.start` 不允许 `None`**

  `start` 已收敛为必需 `int`，相关 fallback 与无意义检查已移除。

- **[B6] `combine` 排序时的隐式 fallback**

  随 B5 自然消除，排序直接使用 `line.start`。

- **[F-IO] 文件 I/O 支持**

  已实现 `Lyrics.load(fp)` / `lyrics.dump(fp)` 与顶层 `load()` / `dump()`。

- **[F-COPY] 深拷贝方法链**

  已实现 `Lyrics.copy()`、`LyricLine.copy()`、`BasicLyricLine.copy()`、`LyricToken.copy()`。

- **[F-SRT] SRT 字幕互转**

  已实现 `Lyrics.to_srt()` / `Lyrics.from_srt()` 与顶层 `dump_srt()` / `parse_srt()`。

- **[F-WEBVTT] WebVTT 字幕互转**

  已实现 `Lyrics.to_webvtt()` / `Lyrics.from_webvtt()` 与顶层 `dump_webvtt()` / `parse_webvtt()`。

### v0.4.x 结构重构

- **[S1] `Lyrics` 双重身份消除**

  移除 `lyrics.lines` 兼容层，统一使用 `UserList` 容器语义。

- **[S2] 时间标签正则去重**

  通过模板函数生成 line / word / generic 三类时间标签正则。

- **[S3] 私有符号跨模块依赖下沉**

  新增 `_utils.py` 承载内部共享 helper。

- **[S4] 公共 Dict 类型去下划线并前移**

  `LyricTokenDict` / `LyricLineDict` / `LyricsDict` 已作为公共类型导出。

- **[S5] `line_filter` 语义收敛为正则**

  `str` 形式统一编译为正则，使用 `pattern.search`。

- **[S6] 杂项清理**

  包括 docstring、注释编号、测试文件命名、序列化 helper 等结构清理。

---

## 已关闭 / 不计划

- **[NEW-INTERP] 逐字时间线性插值填充**

  关闭理由：插值是播放器或音频强制对齐工具的职责，不适合放在解析器中。

- **[NEW-OFFSET-META] `apply_delta` 自动清理 `metadata.offset`**

  关闭理由：显式优于隐式。可考虑新增显式 helper，但不应自动修改 metadata。

- **[NEW-ASYNC] 异步 I/O 支持**

  关闭理由：解析本质是 CPU 同步逻辑，异步 I/O 应由调用方处理。

---

## 极低优先级 / 观望

- **[MF-DUET] Walaoke 对唱扩展**

  支持 `M:` / `F:` / `D:` 前缀标记男 / 女 / 合唱。现实中非常少见，暂不建议投入。

- **[MF-COMMENT] 元数据注释 `[#...]`**

  与当前 `dict[str, str]` metadata 模型冲突，且现实使用率低。除非出现明确用户需求，否则不建议支持。
