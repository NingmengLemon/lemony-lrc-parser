# Design（项目概况、架构方向与取舍）

本文件回答"现在长什么样""打算怎么演进""哪些坑是故意留着不填的"。
历史版本与已落地功能见 [`../CHANGELOG.md`](../CHANGELOG.md)；
社区调研与语料数据见 [`research.md`](research.md)；风险与不计划项见 [`risks.md`](risks.md)。

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
- 文本查找的显式 API：`contains_text()` / `find_text()`（子串、区分大小写）。
- 往返保真度不变量测试：解析器输出必过自己的 `validate()`、`dumps` 一轮收敛、
  格式良好语料的 dump→load 行结构稳定（`tests/test_roundtrip_matrix.py`）。


### 当前设计取舍

- `Lyrics` 是基于 `UserList[LyricLine]` 的容器，同时承担聚合 API 入口职责。
- `LyricLine.start` 已经收敛为必需的 `int`，无时间戳行目前不会进入正常行模型。
- 解析器默认偏宽松：部分异常格式会被跳过或记录 warning，而不是直接失败。
- 行尾时间由最后一个词元（或可选地用下一行开始时间）**推断**而来；若推断结果
  `end <= start`（逐字标签与行首标签矛盾、或零长度行），丢弃该推断并 warning，
  因此解析器不会产出 `validate()` 判为 error 的行。词元自身时间戳原样保留。
- 行首标签与首个词元矛盾时（标签晚于词元时间）按首个词元**归位**，而不是丢弃
  整行 —— 丢弃会让紧随其后的翻译/音译行一起消失。
- metadata 的 value 由**配对方括号**定边界：`[al: Album [Deluxe]]` 读作
  `Album [Deluxe]`；方括号不平衡时整行按正文处理（不猜边界）。
- 标签之后的空白算正文（`[00:01.000]  ` 的正文是 `"  "`），而没有标签的空白行
  仍是分隔符（重置参考行锚点）。
- 相邻时间标签的"相等"视为正常写法（逐字行里空格词元与下一个词共享时间戳），
  静默合并；只有真正递减的乱序标签才 warning。
- `str in <模型>` 保留旧行为但发 `DeprecationWarning`（同一个 `in` 在
  `LyricToken` / `BasicLyricLine` / `LyricLine` / `Lyrics` 上语义各不相同），
  文本查找统一走 `contains_text()` / `find_text()`。
- 内部时间精度是毫秒；输出为百分秒或其他尾数长度时可能有损。
- subtitle 互转会丢弃逐字标签与 metadata，这是格式差异导致的预期行为。
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

### A2：新增 `validation.py`，让验证成为独立子系统 ✅ 已落地 (0.4.0b3)

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


def validate_lyrics(
    lyrics: Lyrics, *, options: ValidationOptions | None = None
) -> list[ValidationIssue]: ...
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

### A5：CLI 作为应用层独立存在 ✅ 已落地 (0.4.0b3)

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
### 待决策 / 已知取舍

> 这些条目的共同点是：**LRC 没有官方规范，所以"正确做法"本身不存在**，只能在
> "保真 / 易用 / 兼容别的实现"之间挑一个，并把理由写下来。每条按
> **现象 → 为什么绕 → 当前选择 → 若要改需要动什么** 组织。

#### 1. 空正文 + 显式区间（`[00:01.000][00:02.000]`）

- **现象**：一行没有正文、却带了行尾时间。空 SRT cue 转 LRC 也会产生这种行。
- **为什么绕**：这个写法与"两个相邻的空占位行"在 LRC 里**完全同形** ——
  `[t1][t2]` 既可以读成"同一行出现在两个时间点"（折叠标签），也可以读成
  "一行从 t1 持续到 t2"。没有任何标记能区分。
- **当前选择**：按"折叠标签"解析（两个空占位行）；写出时保留 `end` 并 warning。
  理由：折叠标签是 LRC 里既有且常用的语义，而"空行 + 区间"在真实语料里
  （6536 份）**一次都没出现**。20k 份随机语料的差分测试显示，这是唯一仍会让
  `dumps` 首轮输出与重新解析结果不同的形状（135/20000），且第二轮起收敛。
- **若要改**：得在 `_finalize_lyrics` / 解析 2c 分支引入启发式（例如"两个标签之间
  没有正文时视为区间"），代价是可能与真实折叠标签冲突。README 的"往返保真度"
  小节已经把这个已知有损场景列出来了。

#### 2. 完全为空的参考行

- **现象**：`reference_lines` 里出现一个既没有正文、也没有任何逐字标签的条目。
- **为什么绕**：写出它只能落成一行孤立的 `[00:01.000]`；解析端遇到"该时间点已存在"
  时会把它当作占位符**忽略**，于是这条参考行必然丢失。
- **当前选择**：干脆不写出（`dump_lrc` 里的 debug 日志），这样 `dumps` 的输出才稳定；
  真实语料里这类条目 **0 条**。
- **若要改**：只能给 LRC 造新语法（例如空的 `<...>` 占位），不值得。

#### 3. `metadata` 用 `dict[str, str]`

- **现象**：同名 key 出现两次时，前面的值被静默覆盖；顺序虽然靠 dict 保住了，但
  重复项丢了。
- **为什么绕**：容器形态有取舍 —— dict 好用但丢重复；`list[tuple[str, str]]` 保真
  但不好用。成熟先例（HTTP 头）走的是第三条路：**有序 multimap + dict 式读取**。
- **当前选择**：暂不改（破坏性变更），常见 key 先给类型提示
  （`MetadataKey` / `MetadataDict` / `COMMON_METADATA_KEYS`）。
- **若要改**：见 `F-META-MULTI`（[roadmap.md](roadmap.md)）与
  [research.md 的容器调研](research.md#重复-key-与类-headers容器设计)，
  计划随 0.5.0 一起做。

#### 4. 方括号不平衡的 metadata value（`[ti: 50% ]off]`）

- **现象**：value 里的 `]` 比 `[` 多（或反之），无法判断 value 从哪里结束。
- **为什么绕**：正则无法表达"配对"（Python `re` 没有递归/平衡组），而引入转义语法
  等于自造方言 —— 社区没有任何实现定义过转义。
- **当前选择**：整行按普通正文处理（不猜边界），写出这类 value 时 warning。
- **若要改**：先改 `research.md` 里记的那条调研结论（目前结论是"不做"）。

#### 5. `zip(..., strict=True)` 与 Python 下限

- **现象**：`strict=` 需要 Python 3.10+，而本库支持 3.9，因此测试里刻意不用它
  （否则 3.9 上直接 `TypeError`）。
- **当前选择**：`requires-python` 保持 `>=3.9,<3.16`；CI 用 3.9–3.14 矩阵验证。
- **若要改**：等下限抬到 3.10 后交给 ruff 的 B905 统一。

#### 6. 乱序 / 负时间戳

- **现象**：真实文件里存在 `start` 递减的行（本次语料 0 例，但历史上见过），以及
  offset 应用后变负的时间戳。
- **当前选择**：解析端**照原样保留**（宽松），由 `validate()` 报告（`unsorted`
  是 error、`duplicate-start` 是 warning）；`apply_delta()` 遇下溢直接抛
  `TimestampUnderflowError` 交给调用方决定。
- **若要改**：见 `F-STRICT`（`ParseOptions.strict=True` 时可升级为异常）。
