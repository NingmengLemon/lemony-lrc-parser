# Feature Ideas for lemony-lrc-parser

本文档记录对项目的功能增强建议，按状态和优先级排序。

> 大部分是 AI 写的，但是窝有在审,,

> 哎呀阿米诺，很多问题就是 lrc 没标准化导致的，看看隔壁 srt / webvtt / ass ,,

---

## 一、已完成 (Completed)

以下条目已在对应版本中修复/实现。

### v0.3.x

- **[B1] ✅ 仅含逐字标签 (尖括号) 的行被误判为参考行**

  [`parser.py:_split_leading_line_timetags`](src/lemony_lrc_parser/parser.py:323) 只匹配 `LINE_TIMETAG_REGEX` (方括号)。当一行以 `<00:01.000>text` 开头时，`_split_leading_line_timetags` 剥离不到任何标签 → `time_tags=[]` → 落入 `if not time_tags` 分支，可能被误判为参考行或孤儿行。

  **修复**: `parse_lrc` 中增加对 `line[0].start is not None` 的判断，以第一个词元 start 作为 `line.start`。

- **[B3] ✅ 参考行格式化时错误传入主行的 `line_end`**

  [`serializer.py:dump_lrc`](src/lemony_lrc_parser/serializer.py:71) 格式化参考行时曾传入了 `line_end=line.end`，导致参考行最后一个词元 `end` 若等于主行 `line.end` 会被错误省略。

  **修复**: 改为传入 `line_end=None`。

- **[B4] ✅ `parse_timetag` 使用严格正则，与解析器宽松行为不一致**

  [`timetag.py:parse_timetag`](src/lemony_lrc_parser/timetag.py:66) 曾使用 `TIMETAG_REGEX_STRICT` (要求三段齐全)，而解析器内部使用 `LINE_TIMETAG_REGEX` (允许省略毫秒、1-6 位尾数)。

  **修复**: 统一使用 `LINE_TIMETAG_REGEX`。

### v0.4.x

- **[B5] ✅ `LyricLine.start` 不允许 `None`**

  [`models.py:LyricLine`](src/lemony_lrc_parser/models.py:172) 的 `start` 改为必需的 `int` (移除默认值和 `None` 支持)。`combine`、`dump_lrc`、`apply_delta` 等处移除不再需要的 `is None` 检查和 warning + skip 逻辑。

- **[B6] ✅ `combine` 排序时 `line.start or 0` 的隐式 fallback**

  随 B5 修复自然消除：`sorted(pool.values(), key=lambda line: line.start)` 不再需要 `or 0` 兜底。

- **[F-IO] ✅ 文件 I/O 支持 (`Lyrics.load(fp)` / `lyrics.dump(fp)`)**

  `Lyrics.load(fp)` / `lyrics.dump(fp)` 已实现，同时顶层 `load()` / `dump()` 便捷函数已加入公共 API。

- **[F-COPY] ✅ 深拷贝方法链**

  `Lyrics.copy()`、`LyricLine.copy()`、`BasicLyricLine.copy()`、`LyricToken.copy()` 均已实现。内部全面用自定义 `.copy()` 替代 `deepcopy`，语义更清晰且性能更优。

- **[F-SRT] ✅ SRT (SubRip) 字幕互转**

  新增 [`subtitle.py`](src/lemony_lrc_parser/subtitle.py) 模块，实现 `Lyrics.to_srt()` / `Lyrics.from_srt()`（及顶层 `dump_srt` / `parse_srt`）。通过 `SubtitleOptions` 控制行尾时间补齐策略、默认时长与参考行输出。

- **[F-WEBVTT] ✅ WebVTT 字幕互转**

  同 F-SRT，实现 `Lyrics.to_webvtt()` / `Lyrics.from_webvtt()`（及顶层 `dump_webvtt` / `parse_webvtt`）。解析时自动跳过 `WEBVTT` 头部与 `NOTE` / `STYLE` / `REGION` 块，并兼容 cue 时间轴的样式设置后缀。

### v0.4.x 结构重构 (Structural Refactor)

以下为一次针对**代码结构组织**的集中重构, 不改变对外行为 (除 `line_filter`
语义收敛外), 主要提升分层清晰度与可维护性:

- **[S1] ✅ `Lyrics` 双重身份消除 (走纯 UserList)**

  移除 [`Lyrics.lines`](src/lemony_lrc_parser/models.py) property/setter.
  过去 `lyrics.lines` 返回自身、setter 又偷偷 deepcopy, 造成 `append` 与
  `lines = [...]` 行为不一致的史山. 现在 `Lyrics` 直接就是 `UserList[LyricLine]`,
  统一用 `lyrics[i]` / `len(lyrics)` / `lyrics.append(...)` / `lyrics.extend(...)`,
  内部批量重排改用 `self.data = ...`.

- **[S2] ✅ 时间标签正则去重 (模板函数生成)**

  [`regex.py`](src/lemony_lrc_parser/regex.py) 原有三份结构雷同的正则
  (`LINE_` / `WORD_` / `GENERIC_`), 现由 `_make_timetag_regex(open, close, prefix)`
  统一生成, 消除复制粘贴漂移风险. 同时删除了导入期的 `_warmup_cache()` 副作用.

- **[S3] ✅ 私有符号跨模块依赖下沉**

  新增内部模块 [`_utils.py`](src/lemony_lrc_parser/_utils.py), 把原先
  `from .timetag import _match_to_ms` 这种"私有函数跨模块导入"下沉为
  `_utils.match_to_ms`, `timetag` 与 `parser` 均从此消费, 命名可见性与真实用法一致.

- **[S4] ✅ 公共 Dict 类型去下划线并前移**

  `_LyricTokenDict` / `_LyricLineDict` / `_LyricsDict` 改名为
  `LyricTokenDict` / `LyricLineDict` / `LyricsDict`, 前移到被引用处之前,
  并从包顶层导出 (它们本就是 `to_dict()` 的公共返回类型).

- **[S5] ✅ `line_filter` 语义收敛为正则**

  [`ParseOptions`](src/lemony_lrc_parser/models.py) 的 `line_filter` 不再区分
  "字符串子串" 与 "正则" 两套语义, 统一按正则理解: `str` 会在 `__post_init__`
  中被 `re.compile`, 之后一律 `pattern.search`. 需精确子串匹配时用 `re.escape`.
  这是本次唯一的对外行为变化.

- **[S6] ✅ 杂项清理**

  - `exceptions.py` 全部补齐 docstring, 并说明 `ProgrammingError` 刻意不继承
    `LyricsParserError` 的设计意图.
  - `BasicLyricLine` 从错误的 `#:` 变量文档语法改为正规 class docstring.
  - `serializer.py` 抽取 `write_line_tag` helper, 收敛重复的行标签写入逻辑.
  - 修正 `parser.py` 中重复的 `# 2b.` 注释编号 (2b/2c/2d).
  - `models.py` 模块 docstring 改为如实描述**充血模型 / 聚合层**定位.
  - 测试组织: `test_construct_lrc_offset.py` 重命名为 `test_offset.py`, 与其余
    `test_<模块>.py` 命名约定对齐.

### 部分完成

- **[F-REPR] 🔶 自定义 `__repr__` 改善调试体验** (部分完成)

  所有类目前均使用默认的 ``__repr__``: :class:`LyricToken` 和 :class:`LyricLine`
  使用 dataclass 自动生成的多字段 repr, :class:`Lyrics` 使用 ``UserList`` 的列表 repr。
  **待做**: 为三个类分别实现更紧凑的自定义 ``__repr__`` (如 ``LyricToken('hello', 1000, 2000)``)。

- **[F-CONTAINS] 🔶 `__contains__` 增强** (部分完成)

  `LyricToken.__contains__` 和 `BasicLyricLine.__contains__` 已实现字符串子串搜索。`BasicLyricLine` 因继承自 `list` 已天然支持 `token in line`。
  **待做**: `Lyrics.__contains__` 尚未实现。

- **[F-DICT] 🔶 `to_dict()` / `from_dict()` 序列化** (部分完成)

  :class:`LyricToken`、:class:`BasicLyricLine`、:class:`LyricLine`、:class:`Lyrics`
  四个类的 ``to_dict()`` / ``from_dict()`` 均已实现, 可往返转换。
  **待做**: 便捷 ``to_json()`` 方法尚未实现。

---

## 二、设计改进 (Design Improvements)

### 🔴 高优先级

- **[B2] `format_timetag` 在 `tail_digits < 3` 时存在精度丢失**

  [`timetag.py:format_timetag`](src/lemony_lrc_parser/timetag.py:58) 中 `tail = millis // 10 ** (3 - tail_digits)` — 555ms 格式化为 `55` (百分秒)，解析回来变成 550ms，丢失 5ms。

  这是文档问题而非实现问题。Wikipedia 等参考网站以及网易云/QQ 音乐抓取的 lrc 精度都只到百分秒；`tail_digits > 3` 同理也没意义，因为内部精度只到毫秒。~~甚至SPL文档里也是~~

  **建议**: 在文档和 docstring 中明确标注此为**有损截断**，并在 `tail_digits < 3` 时发出 `warnings.warn`。

### 🟢 低优先级

- **[B7] 缺少逐字时间戳与行时间范围的一致性校验**

  当前没有任何代码检查 `LyricToken.start` / `LyricToken.end` 是否落在所属 `LyricLine.start` ~ `LyricLine.end` 范围内。恶意或损坏的 LRC 文件可能产生 `word.start < line.start` 的数据。

  **优先级**: 低。

---

## 三、功能增强 (Feature Enhancements)

### 🔴 高优先级

- **[F-STRICT] 解析严格模式 (`ParseOptions.strict: bool`)**

  开启后以下情况从 warning 升级为抛出 `InvalidLyricsError`:
  - 行首没有时间标签的孤立行
  - 时间标签不单调递增 (行级)
  - `start=None` 的行
  - metadata key 不符合标准格式
  - 同一文件中有重复的 `[offset:...]` 标签

- **[F-DURATION] `LyricLine.duration` 属性**

  ```python
  @property
  def duration(self) -> int | None:
      if self.start is not None and self.end is not None:
          return self.end - self.start
      return None
  ```

- **[F-RANGE] 时间范围查询 `Lyrics.lines_in_range()`**

  ```python
  def lines_in_range(self, start_ms: int, end_ms: int) -> list[LyricLine]:
      """返回所有时间戳完全或部分落在 [start_ms, end_ms] 内的行."""
  ```

### 🟡 中优先级

- **[F-MUTATE] `Lyrics` 安全变更方法**

  `Lyrics` 现为 `UserList`, 直接 `lyrics.append(...)` / `lyrics[i] = ...`
  会绕过按时间排序/一致性维护:

  ```python
  lyrics.insert_line(line: LyricLine)   # 插入后自动排序
  lyrics.remove_line(index: int)         # 安全删除
  ```

- **[F-COMBINE-ALL] 批量合并 (`combine_all`)**

  ```python
  main.combine_all([trans_zh, trans_ja, translit])
  # 等价于 main + trans_zh + trans_ja + translit
  ```

  链式 `+` 也能做到，但 `combine_all` 语义更清晰。

- **[F-VALIDATE] 数据一致性验证 API `Lyrics.validate()`**

  检查:
  - 时间戳是否严格递增
  - 没有 `start is None` 的行
  - 逐字标签时间是否在行时间范围内
  - metadata key 是否合法

  返回 `list[ValidationError]` 或抛出异常。

- **[NEW-ERROR-LINE] 解析错误时包含行号信息**

  当前 `InvalidLyricsError` 等异常不包含出错行的行号，调试多行 LRC 文件时定位困难。建议异常消息中附带行号：

  ```python
  raise InvalidLyricsError(f"Line 42: unexpected sequence length")
  ```

  可结合 `enumerate(raw_line in lrc.strip().splitlines())` 实现。

- **[NEW-STATS] `Lyrics.stats` 统计信息属性**

  作为 frozen dataclass 实现，以 property 方式暴露：

  ```python
  @dataclass(frozen=True)
  class LyricsStats:
      lines: int
      words: int
      total_duration_ms: int | None
      avg_line_duration_ms: float | None
      has_byword: bool
      has_reference_lines: bool
      metadata_keys: list[str]
      format_type: LrcFormat

  >>> lyrics.stats
  LyricsStats(
      lines=42,
      words=384,
      total_duration_ms=235000,
      avg_line_duration_ms=5595.0,
      has_byword=True,
      has_reference_lines=True,
      metadata_keys=['ti', 'ar', 'al'],
      format_type=LrcFormat.ENHANCED_LRC,
  )
  ```

  方便用户快速了解歌词结构，也可用于 CI 校验。

- **[NEW-DETECT] LRC 格式自动检测**

  使用枚举类型表示格式：

  ```python
  class LrcFormat(enum.Enum):
      SIMPLE_LRC = "Simple LRC"
      ENHANCED_LRC = "Enhanced LRC"
      SPL = "SPL"

  >>> lyrics.format_type
  LrcFormat.ENHANCED_LRC
  ```

  检测逻辑: 以是否存在 `<mm:ss.xxx>` 逐字标签为主要依据 (注意: metadata 标签不是逐字 LRC 特有的，不能作为判断依据)。

  > `Salt Player 歌词格式（简称“SPL”），基于且兼容（增强型）LRC，一种阅读友好的歌词格式。`, SPL 只是椒盐音乐作者自己定的一个lrc语法标准, 真的能单独算作一个format吗

- **[MF-FUZZY] 合并歌词时的模糊匹配** 🚀

  先走一遍完美匹配的合并，然后对剩余行模糊配对（时间相近的行自动关联）。实际使用中比 Walaoke 对唱 / `[#...]` 注释有用得多。

### 🟢 低优先级

- **[F-META-TYPE] Metadata 值类型辅助**

  ```python
  lyrics.get_metadata_int("offset")    # → int | None
  lyrics.get_metadata_float("length")  # → float | None
  ```

- **[F-META-KEY] METATAG key 支持更宽泛字符集 / 可配置**

  当前 `METATAG_REGEX` 限制 key 为 `[a-zA-Z][a-zA-Z0-9]{1,15}`，不支持 `_`、`-`。某些非标准 LRC 变体可能使用这些字符。

  **建议**: 提供可配置的 `meta_key_pattern` 参数。

- **[F-EXPORT-OTHER] 导出为其他字幕格式**

  - `to_ass()` — Advanced SubStation Alpha
  - `to_vtt()` — 若与 F-WEBVTT 合并则去重

- **[F-LOGGING] `logger.warning` → `warnings.warn` 审计**

  部分场景 `logger.warning` 的力度可能不够（如用户不配置 logging 则看不到），酌情将面向最终用户的警告迁移到 `warnings.warn`。

- **[NEW-ROUNDTRIP] 轮转一致性 (Roundtrip Fidelity) 保证**

  目标是 `llp.loads(llp.dumps(lyrics))` 在语义上等价于原始 `lyrics`。当前已知 `tail_digits < 3` 时有精度丢失 (B2)，以及排序可能导致 metadata 键顺序变化等。可建立 roundtrip test suite 持续跟踪。

- **[NEW-SEARCH] `Lyrics.search(text: str)` 全文搜索**

  ```python
  >>> lyrics.search("love")
  [LyricLine(start=18684, text="We're no strangers to love"), ...]
  ```

  简单遍历所有行做子串匹配，返回匹配的 `LyricLine` 列表。

- **[NEW-UNSYNCED] 未同步行收集 (`lyrics.unsynced_lines`)**

  与 B5 配套：将无法确定时间戳的行统一收集到 `lyrics.unsynced_lines: list[str]`，而非静默丢弃。用户可自行决定如何处理它们。

- **[NEW-CLI] CLI 入口 (`python -m lemony_lrc_parser`)**

  ```bash
  # 验证 LRC 文件
  python -m lemony_lrc_parser validate song.lrc

  # 应用偏移
  python -m lemony_lrc_parser offset song.lrc --delta 500 -o song_offset.lrc

  # 合并翻译
  python -m lemony_lrc_parser combine main.lrc trans.lrc -o combined.lrc
  ```

  对标 `python -m json.tool`，方便非 Python 用户使用。

---

## 四、已关闭 / 不计划 (Closed / Not Planned)

以下条目经评审后决定不纳入开发计划。

- **[NEW-INTERP] ~~逐字时间线性插值填充~~**

  ~~对于 `fill_implicit_line_end=True` 的扩展：不仅填充 `line.end`，还能对缺失 `word.start`/`word.end` 的逐字行做均匀插值。~~

  **关闭理由**: 插值填充是播放器在播放时做的事，不属于解析器职责范围。线性填充效果差且实现无意义。

  > 不过有另一个实验项目是用音频强制对齐来实现逐字填充，跟这里关系不大。

- **[NEW-OFFSET-META] ~~`apply_delta` 自动清理 `metadata.offset`~~**

  ~~README 提示用户"记得手动清理"——可添加 `clean_metadata_offset: bool = True` 参数使其成为内置行为。~~

  **关闭理由**: 显式优于隐式。用户应自行管理 metadata。

- **[NEW-ASYNC] ~~异步 I/O 支持~~**

  ~~`lyrics = await Lyrics.aloads(lrc_text)` 等异步接口。~~

  **关闭理由**: 纯 CPU 解析本质上是同步的，I/O 异步交给库的用户处理即可，不需要库层面封装。

---

## 五、极低优先级 / 观望 (Maybe Someday)

可能永远不会做，但保留记录以供将来参考。

- **[MF-DUET] Walaoke 对唱扩展**

  来自 Wikipedia: 支持 `M:` / `F:` / `D:` 前缀标记男/女/合唱行，用于不同颜色显示。

  > 在现实中完全没见到过。最低优先级，或 Closed as not planned.

- **[MF-COMMENT] 元数据注释 `[#...]`**

  来自 Wikipedia 核心格式，tag type 可能为 `#` 表示注释。多个注释与现有 `dict[key, value]` 模型冲突。

  > 在现实中完全没见到过。

---

## 六、优先级汇总

| 状态 | 编号 | 简述 |
|------|------|------|
| ✅ 已完成 | B1 | 仅逐字标签行被误判为参考行 (v0.3.x) |
| ✅ 已完成 | B3 | 参考行格式化错误传入 `line_end` (v0.3.x) |
| ✅ 已完成 | B4 | `parse_timetag` 严格/宽松正则不一致 (v0.3.x) |
| ✅ 已完成 | B5 | `LyricLine.start` 不允许 `None` (v0.4.x) |
| ✅ 已完成 | B6 | `combine` 排序 `or 0` fallback 移除 (v0.4.x) |
| ✅ 已完成 | F-IO | 文件 I/O `load(fp)` / `dump(fp)` (v0.4.x) |
| ✅ 已完成 | F-COPY | 深拷贝方法链替代 `deepcopy` (v0.4.x) |
| ✅ 已完成 | F-SRT | 导出/解析 SRT 字幕格式 (v0.4.x) |
| ✅ 已完成 | F-WEBVTT | 导出/解析 WebVTT 字幕格式 (v0.4.x) |
| 🔶 部分 | F-REPR | 自定义 `__repr__` 全部未实现，均使用默认 repr |
| 🔶 部分 | F-CONTAINS | Token/Line `__contains__` 已实现; Lyrics 待做 |
| 🔶 部分 | F-DICT | `to_dict()`/`from_dict()` 已实现; `to_json()` 待做 |
| 🔴 高 | B2 | `format_timetag` 精度丢失：文档标注 + `warnings.warn` |
| 🔴 高 | F-STRICT | 解析严格模式 |
| 🔴 高 | F-DURATION | `LyricLine.duration` 属性 |
| 🔴 高 | F-RANGE | `Lyrics.lines_in_range()` 时间范围查询 |
| 🟡 中 | F-MUTATE | `Lyrics` 安全变更方法 |
| 🟡 中 | F-COMBINE-ALL | 批量合并 `combine_all` |
| 🟡 中 | F-VALIDATE | `Lyrics.validate()` 一致性验证 |
| 🟡 中 | NEW-ERROR-LINE | 解析错误附带行号 |
| 🟡 中 | NEW-STATS | `Lyrics.stats` 统计信息 (frozen dataclass, property) |
| 🟡 中 | NEW-DETECT | LRC 格式自动检测 (使用枚举) |
| 🟡 中 | MF-FUZZY | 模糊匹配合并 |
| 🟢 低 | B7 | 逐字时间戳与行范围一致性校验 |
| 🟢 低 | F-META-TYPE | Metadata 值类型辅助 |
| 🟢 低 | F-META-KEY | meta key 可配置字符集 |
| 🟢 低 | F-EXPORT-OTHER | 导出 ASS 等其他字幕格式 |
| 🟢 低 | F-LOGGING | `warnings.warn` 审计 |
| 🟢 低 | NEW-ROUNDTRIP | 轮转一致性保证 |
| 🟢 低 | NEW-SEARCH | 全文搜索 `Lyrics.search()` |
| 🟢 低 | NEW-UNSYNCED | 未同步行收集 |
| 🟢 低 | NEW-CLI | CLI 入口 `python -m lemony_lrc_parser` |
| ❌ 已关闭 | NEW-INTERP | 逐字时间线性插值填充 |
| ❌ 已关闭 | NEW-OFFSET-META | `apply_delta` 自动清理 metadata.offset |
| ❌ 已关闭 | NEW-ASYNC | 异步 I/O 支持 |
| ⚪ 观望 | MF-DUET | Walaoke 对唱扩展 |
| ⚪ 观望 | MF-COMMENT | 元数据注释 `[#...]` |
