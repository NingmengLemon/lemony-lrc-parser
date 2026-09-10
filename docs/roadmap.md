# Roadmap（路线图与候选功能）

本文件只谈**还没做**的事：优先级路线图、候选功能与设计改进、以及暂缓/观望项。
条目 ID（`F-*` / `NEW-*` / `MF-*` / `MY-*`）保持不变，代码注释与 CHANGELOG 均引用它们。

---

## 优先级路线图

### P0 / 高优先级：建议优先做

| ID | 主题 | 类型 | 价值 | 状态 |
| --- | --- | --- | --- | --- |
| F-VALIDATE | 数据一致性验证 API | 质量 / DX | 高 | ✅ v0.4.0b3 |
| NEW-ERROR-LINE | 解析错误包含行号与原始行 | 可诊断性 | 高 | ✅ v0.4.0b3 |
| NEW-CLI | CLI 入口 | 工具化 | 高 | ✅ v0.4.0b3 |
| B7 | 逐字时间戳与行时间范围一致性校验 | 正确性 | 高 | ✅ v0.4.0b3 |
| NEW-ROUNDTRIP | Roundtrip Fidelity 测试矩阵 | 回归保障 | 高 | ✅ 0.4.0 |

### P1 / 中优先级：稳定核心后推进

| ID | 主题 | 类型 | 价值 | 备注 |
| --- | --- | --- | --- | --- |
| NEW-PRESERVE-STYLE | 写回时保留原文件风格 | 保真性 | 中高 | CRLF / 尾数位数 / 空行风格；100% 语料写回后与源文件不同 |
| F-STRICT | 解析严格模式 | 可控性 | 中高 | 最好建立在 `validate()` 与行号错误之上 |
| F-RANGE | 时间范围查询 | API | 中 | 对播放器、剪辑、字幕片段提取有用 |
| F-MUTATE | 安全变更方法 | API | 中 | 降低用户直接操作 list 破坏排序的概率 |
| NEW-SEARCH | 全文搜索 | API | 中 | `find_text()` 已覆盖子串；正则 / 跨行 / 结果定位待做 |
| MF-FUZZY | 合并歌词时模糊匹配 | 实用增强 | 中 | 翻译歌词时间轴常有轻微偏差 |
| F-REPR | 自定义紧凑 repr | DX | 中 | 调试体验改善明显 |
| NEW-PARSE-REPORT | 解析报告对象 | 可诊断性 | 中 | 把"丢了哪些行 / 为什么丢"从日志变成可读数据 |

### P2 / 低优先级：有需求再做

| ID | 主题 | 类型 | 价值 | 备注 |
| --- | --- | --- | --- | --- |
| F-META-MULTI | metadata 改成有序 multimap | API | 中高 | 破坏性变更，计划随 0.5.0；先做调研见 research.md |
| F-DURATION | `LyricLine.duration` 属性 | API | 低中 | 简单但要定义 `end is None` 的语义 |
| F-CONTAINS | `Lyrics.__contains__` 增强 | API | — | ✅ 0.4.0 以 `contains_text()` / `find_text()` 落地（不扩大 `in`） |
| F-COMBINE-ALL | 批量合并 | API | 低 | 语义清晰但链式合并已可覆盖 |
| NEW-STATS | `Lyrics.stats` | 信息辅助 | 低中 | 可基于 `validate()` / 格式检测共同实现 |
| NEW-DETECT | LRC 格式自动检测 | 信息辅助 | 低 | “SPL 是否单独算格式”需要谨慎 |
| F-META-TYPE | metadata 值类型辅助 | API | 低 | 可做成轻量 helper（`MetadataKey` / `MetadataDict` 已提供类型提示） |
| F-META-KEY | metadata key 可配置 | 兼容性 | 低 | 可能扩大歧义 |
| MF-COMMENT-LINE | `#` 开头的注释行 | 兼容性 | 低 | 部分实现支持（AMLL 文档提及）；与现有"孤儿行"策略需要协调 |
| F-EXPORT-OTHER | ASS 等其他字幕格式导出 | 格式扩展 | 低 | ASS 支持复杂样式，可能超出当前库定位 |
| F-LOGGING | warning / logging 审计 | 体验 | 低 | 不宜过度打扰用户 |

---
## 候选功能与设计改进

### 已落地 (设计稿已迁出)

下面这些条目已经实现, 设计讨论与回归细节见
[CHANGELOG.md](../CHANGELOG.md) 里 0.4.0 一节; 这里不再保留设计稿, 以免
出现"文档描述与代码不同步"的第二事实来源:

- `F-VALIDATE` → `validation.py` (`validate_lyrics` / `Lyrics.validate`)。
- `NEW-ERROR-LINE` → `InvalidLyricsError.line_no` / `.raw_line`。
- `NEW-CLI` → `lemonyrics` / `python -m lemony_lrc_parser`。
- `B7` → `_check_line_tokens()` 的词元越界与单调性检查。
- `NEW-ROUNDTRIP` → `tests/test_roundtrip_matrix.py` (三条不变量 + 随机语料)。
- `F-CONTAINS` → `contains_text()` / `find_text()` 显式 API + `in` 的
  `DeprecationWarning` (结论: 不扩大 `in` 的语义)。

### NEW-PRESERVE-STYLE：写回时保留原文件风格

动机（真实语料审计）：6536 份 `.lrc` 里 **100%** 写回后与源文件不同 —— 行尾从
CRLF 变成 LF、2 位尾数（占全部时间标签的 6.7%）被补成 3 位、行间空行按
`line_separator` 重排。解析端完全正确，问题在"重写别人的曲库"这一使用场景。

建议：

- `SerializationOptions` 增加 `line_ending`（`"auto"` / `"lf"` / `"crlf"`）。
- 增加按"原文件探测到的风格"写回的入口，例如
  `Lyrics.loads(text).dumps(style=StyleDetection.from_text(text))`；
  或提供 `detect_style(text) -> DocumentStyle` 独立函数（NEW-DETECT 的一部分）。
- 尾数位数保持按行 / 按词探测（同一文件里 2 位与 3 位混用很常见）。
- 仍要允许显式覆盖，避免"想统一格式却改不动"。

### NEW-PARSE-REPORT：解析报告对象

动机：目前"某行被丢弃 / 被归位 / 被降级为参考行"只体现在日志里，调用方拿不到
结构化数据（真实语料里存在孤儿行、被归位的行首标签等形态）。

建议：

- `parse_lrc(text, options=...)` 之外提供 `parse_with_report(text) -> (Lyrics, ParseReport)`，
  或让 `ParseOptions.collect_report = True`。
- `ParseReport` 提供：被丢弃的行（原文 + 行号 + 原因）、被归位的时间标签、
  被当作参考行挂载的行数、metadata 提取结果等。
- 与 `F-STRICT` 天然互补：报告是"事后审计"，strict 是"当场拒绝"。

### MF-COMMENT-LINE：`#` 开头的注释行

AMLL 的格式文档提到"部分实现允许 `#` 前缀的注释行"（见 References）。当前行为是：
`#` 行没有时间标签也没有锚点时按孤儿行告警丢弃，有锚点时会被挂成参考行 ——
两者都不理想。若要做，需要与"孤儿行 / 参考行"策略一起定：建议把 `#` 行识别为
注释并整行忽略（不进参考行、不发告警）。

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

### ~~F-DICT-JSON~~（不计划）

结论（维护者决定）：**不做 `to_json()` / `from_json()`**。`to_dict()` / `from_dict()`
已经足够，产出的 dict 交给调用方自行 `json.dumps(..., ensure_ascii=False)`；
再包一层只会把"JSON schema 是否稳定"变成库的兼容负担（见
[risks.md](risks.md#6-json-schema-一旦公开可能形成兼容负担)）。
`F-META-MULTI` 落地时，`to_dict()` 仍保持"有损但方便"的出口。

### F-META-MULTI：metadata 改成有序 multimap（破坏性，目标 0.5.0）

- **动机**：`dict[str, str]` 会静默丢掉同名 key 的先前值（`[ti: A]` + `[ti: B]` →
  只剩 `B`），且无法保留注释/重复项。
- **调研**（见 [research.md](research.md#重复-key-与类-headers容器设计)）：
  HTTP 头这套"同名可重复"的成熟容器**都不是裸 list**，而是
  "有序 + dict 式读取 + 全量枚举"：werkzeug `Headers`（`getlist()` / `add()` /
  `set()`，迭代产出全部 `(key, value)`）、`httpx.Headers`（`get_list()` /
  `multi_items()`）、`multidict.CIMultiDict`（`getall()`）。
- **建议做法**：

  ```python
  class Metadata(Mapping[str, str]):  # 保持 dict 式读取
      def getlist(self, key: str) -> list[str]: ...
      def add(self, key: str, value: str) -> None: ...  # 追加 (保留重复)
      def set(self, key: str, value: str) -> None: ...  # 替换 (去重)
      def items(self) -> list[tuple[str, str]]: ...  # 全部, 含重复
  ```

  同时：`to_dict()`（有损，后者覆盖）保持不变，新增 `to_pairs()` 做无损导出；
  `from_dict()` 继续接受 dict / `MetadataDict`。
- **迁移**：0.5.0 里 `Lyrics.metadata` 换成 `Metadata`，但保持
  `== dict`、`dict(lyrics.metadata)`、`meta["ti"]`、`meta.get()`、`.update()` 等
  既有写法可用，并在 0.4.x 的 changelog 里提前公告。

### F-REPR：自定义紧凑 repr

当前默认 repr 对嵌套歌词较冗长。建议：

```python
LyricToken("hello", start=1000, end=1500)
LyricLine(start=1000, end=3000, text="hello...", refs=1)
Lyrics(lines=42, metadata={"ti": "...", "ar": "..."})
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

### ~~F-CONTAINS~~ (已落地)

结论与最初设想不同: 不扩大 `in` 的语义, 而是提供显式 API ——
`Lyrics.contains_text()` / `Lyrics.find_text()` /
`LyricLine.contains_text(include_reference_lines=...)`, 同时让 `str in <模型>`
保留旧行为并发 `DeprecationWarning`。详见 CHANGELOG。

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
def get_metadata_float(
    self, key: str, default: float | None = None
) -> float | None: ...
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
def metadata_offset_ms(self) -> int | None: ...  # 解析 [offset:...], 非法时 None
def apply_metadata_offset(self) -> Lyrics: ...  # 等价于 apply_delta(-offset)
```

这样既保持"显式优于隐式"，又降低用户自己解析 `[offset:...]` 的重复成本。

**符号必须写清楚**（调研见 [research.md](research.md#offset-标签的正负语义)）：
LRC 的 `[offset: +N]` 表示"歌词整体提前 N 毫秒"，即时间戳 `-= N`；而本库的
`apply_delta(+ms)` 是"时间戳 `+= ms`"（更晚），**两者符号相反**。所以：

```python
shifted = lyrics.apply_delta(-int(lyrics.metadata.get("offset", 0)))
```

这条换算已经写成测试（`tests/test_offset.py::TestLrcOffsetConvention`），
即使不做 helper，用户也不会踩错符号。另外注意有播放器**完全忽略** offset，
所以"要不要应用"应该由调用方决定。

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
## 极低优先级 / 观望

- **[MF-DUET] Walaoke 对唱扩展**

  支持 `M:` / `F:` / `D:` 前缀标记男 / 女 / 合唱。现实中非常少见，暂不建议投入。

- **[MF-COMMENT] 元数据注释 `[#...]`**

  与当前 `dict[str, str]` metadata 模型冲突，且现实使用率低。除非出现明确用户需求，否则不建议支持。
