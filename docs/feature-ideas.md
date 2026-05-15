# Feature Ideas for lemony-lrc-parser

本文档记录对项目的功能增强建议，按类型和优先级排序。

> 大部分是 AI 写的，但是窝有在审,,

> 哎呀阿米诺，很多问题就是 lrc 没标准化导致的，看看隔壁 srt / webvtt / ass ,,

---

## 一、设计缺陷 (Bugs)

### 已修复 (v0.3.x)

- **[B1] ✅ 仅含逐字标签 (尖括号) 的行被误判为参考行**
  [`parser.py:_split_leading_line_timetags`](src/lemony_lrc_parser/parser.py:294) 只匹配 `LINE_TIMETAG_REGEX` (方括号)。当一行以 `<00:01.000>text` 开头时，`_split_leading_line_timetags` 剥离不到任何标签 → `time_tags=[]` → 落入 `if not time_tags` 分支，可能被误判为参考行或孤儿行。
  **修复**: `parse_lrc` 中增加对 `line[0].start is not None` 的判断，以第一个词元 start 作为 `line.start`。

- **[B3] ✅ `_format_words` 对参考行错误传入主行的 `line_end`**
  [`serializer.py:_format_words`](src/lemony_lrc_parser/serializer.py:86) 格式化参考行时传入了 `line_end=line.end`，导致参考行最后一个词元 `end` 若等于主行 `line.end` 会被错误省略。参考行没有独立的行尾标签输出。
  **修复**: 改为传入 `line_end=None`。

- **[B4] ✅ `parse_timetag` 使用严格正则，与解析器宽松行为不一致**
  [`timetag.py:parse_timetag`](src/lemony_lrc_parser/timetag.py:66) 曾使用 `TIMETAG_REGEX_STRICT` (要求三段齐全)，而解析器内部使用 `LINE_TIMETAG_REGEX` (允许省略毫秒、1-6 位尾数)。
  **修复**: 统一使用 `LINE_TIMETAG_REGEX`。

### 待处理

- **[B2] `format_timetag` 在 `tail_digits < 3` 时存在精度丢失**
  [`timetag.py:format_timetag`](src/lemony_lrc_parser/timetag.py:55) 中 `tail = millis // 10 ** (3 - tail_digits)` — 555ms 格式化为 `55` (百分秒)，解析回来变成 550ms，丢失 5ms。
  > 文档问题，不用改实现。实际上 Wikipedia 等参考网站以及网易云/QQ 音乐抓取的 lrc 精度都只到百分秒。`tail_digits > 3` 同理也没意义，内部精度只到毫秒。
  **建议**: 在文档和 docstring 中明确标注此为**有损截断**，或在 `tail_digits < 3` 时发出 `warnings.warn`。

- **[B5] `LyricLine.start` 允许 `None`，但 synced lyrics 不应有无时间戳行**
  [`models.py:LyricLine`](src/lemony_lrc_parser/models.py:106) 的 `start: int | None = None`。当前 `combine`、`dump_lrc`、`apply_delta` 等多处以 warning + skip 方式静默处理。
  > 我们的库面向的就是 synced lyrics。或许可以把 unsynced 行单独收集到 `lyrics.unsynced_lines: list[str]`，同时让 `LyricLine.start` 不允许为 `None`。
  **优先级**: 中

- **[B6] `combine` 排序时 `line.start or 0` 的隐式 fallback**
  [`models.py:combine`](src/lemony_lrc_parser/models.py:199): `sorted(pool.values(), key=lambda line: line.start or 0)` — `or 0` 是对类型系统的兜底，但若 B5 修复后就不再需要。
  > 这个 `or 0` 是给类型系统的兜底，synced lyrics 不应有无时间戳行。B5 修完后自然消除。
  **优先级**: 随 B5 一起处理

- **[B7] 缺少逐字时间戳与行时间范围的一致性校验**
  当前没有任何代码检查 `LyricToken.start` / `LyricToken.end` 是否落在所属 `LyricLine.start` ~ `LyricLine.end` 范围内。恶意或损坏的 LRC 文件可能产生 `word.start < line.start` 的数据。
  > 可以加，但优先级降低。
  **优先级**: 低

---

## 二、功能增强提案 (Features)

### 🔴 高优先级

- **[F-IO] 文件 I/O 支持 (`Lyrics.load(fp)` / `lyrics.dump(fp)`)**
  对标 `json.load` / `json.dump`，接受 file-like object (非路径字符串)：

  ```python
  # 读取
  with open("song.lrc", encoding="utf-8") as f:
      lyrics = Lyrics.load(f)

  # 写入
  with open("song_offset.lrc", "w", encoding="utf-8") as f:
      lyrics.dump(f)
  ```

- **[F-REPR] 自定义 `__repr__` 改善调试体验**
  当前依赖 dataclass 自动生成的 `__repr__`，输出冗长难读。建议：

  ```python
  >>> token = LyricToken(content="hello", start=1000, end=2000)
  >>> token
  LyricToken('hello', 1000→2000)

  >>> line = LyricLine(start=1000, content=[token])
  >>> line
  LyricLine(start=1000, text='hello', words=1, refs=0)

  >>> lyrics
  Lyrics(lines=42, metadata_keys=['ti', 'ar', 'al'])
  ```

- **[F-DICT] `Lyrics.to_dict()` / `Lyrics.from_dict()` 以及 `to_json()`**

  ```python
  lyrics.to_dict()        # → dict，可 JSON 序列化，用于 API 传输
  Lyrics.from_dict(d)     # ← 从 dict 还原
  lyrics.to_json()        # 便捷封装
  ```

- **[F-SRT] 导出为 SRT 字幕格式**

  ```python
  lyrics.to_srt()  # → SubRip 字幕格式字符串
  ```

  适用场景：将歌词用于视频字幕制作。

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
  当前直接操作 `lyrics.lines` 会绕过排序/一致性维护:

  ```python
  lyrics.insert_line(line: LyricLine)   # 插入后自动排序
  lyrics.remove_line(index: int)         # 安全删除
  ```

- **[F-WEBVTT] 导出为 WebVTT 格式**

  ```python
  lyrics.to_webvtt()  # → WebVTT 字幕格式字符串
  ```

- **[F-COMBINE-ALL] 批量合并 (`combine_all`)**

  ```python
  main.combine_all([trans_zh, trans_ja, translit])
  # 等价于 main + trans_zh + trans_ja + translit
  ```

  > 链式 `+` 也能做到，但 `combine_all` 语义更清晰。

- **[F-CONTAINS] `__contains__` 增强**
  让 Token、Line、Lyrics 支持 `"string" in obj`:
  - `"word" in token` → `"word" in token.content`
  - `"substring" in line` → `"substring" in line.text`
  - `"substring" in lyrics` → `any("substring" in line.text for line in lyrics)`
  - `token in line.content` → 需要 `BasicLyricLine` 继承自 `list`

- **[F-VALIDATE] 数据一致性验证 API `Lyrics.validate()`**
  检查:
  - 时间戳是否严格递增
  - 没有 `start is None` 的行
  - 逐字标签时间是否在行时间范围内
  - metadata key 是否合法
  返回 `list[ValidationError]` 或抛出异常。

### 🟢 低优先级

- **[F-META-TYPE] Metadata 值类型辅助**

  ```python
  lyrics.get_metadata_int("offset")    # → int | None
  lyrics.get_metadata_float("length")  # → float | None
  ```

  > 手动 `int()` 怎么你了 ()

- **[F-COPY] `Lyrics.copy()` 方法**
  `deepcopy` 的便捷封装，语义更清晰：

  ```python
  def copy(self) -> Lyrics:
      from copy import deepcopy
      return deepcopy(self)
  ```

- **[F-META-KEY] METATAG key 支持更宽泛字符集 / 可配置**
  当前 `METATAG_REGEX` 限制 key 为 `[a-zA-Z][a-zA-Z0-9]{1,15}`，不支持 `_`、`-`。某些非标准 LRC 变体可能使用这些字符。
  > 真的有可能吗,, 可配置的 `meta_key_pattern` 倒是可以。

- **[F-EXPORT-OTHER] 导出为其他字幕格式**
  - `to_ass()` — Advanced SubStation Alpha
  - `to_vtt()` — 若与 F-WEBVTT 合并则去重

- **[F-LOGGING] `logger.warning` → `warnings.warn` 审计**
  部分场景 `logger.warning` 的力度可能不够（如用户不配置 logging 则看不到），酌情将面向最终用户的警告迁移到 `warnings.warn`。

---

## 三、极低优先级 / 观望 (Maybe Someday)

- **[MF-DUET] Walaoke 对唱扩展**
  来自 Wikipedia: 支持 `M:` / `F:` / `D:` 前缀标记男/女/合唱行，用于不同颜色显示。
  > 在现实中完全没见到过，最低优先级。或 Closed as not planned.

- **[MF-COMMENT] 元数据注释 `[#...]`**
  来自 Wikipedia 核心格式，tag type 可能为 `#` 表示注释。多个注释与现有 `dict[key, value]` 模型冲突。
  > 在现实中完全没见到过,,

- **[MF-FUZZY] 合并歌词时的模糊匹配**
  先走一遍完美匹配的合并，然后对剩余行模糊配对（时间相近的行自动关联）。
  > 实现复杂度较高，收益存疑。

---

## 四、新 Idea (本次整理新增)

以下 idea 基于对项目源码的完整审查提出。

### 🟡 中优先级

- **[NEW-ERROR-LINE] 解析错误时包含行号信息**
  当前 `InvalidLyricsError` 等异常不包含出错行的行号，调试多行 LRC 文件时定位困难。建议异常消息中附带行号：

  ```python
  raise InvalidLyricsError(f"Line 42: unexpected sequence length")
  ```

  可结合 `enumerate(raw_line in lrc.strip().splitlines())` 实现。

- **[NEW-STATS] `Lyrics.stats()` 统计信息**

  ```python
  >>> lyrics.stats()
  LyricsStats(
      lines=42,
      words=384,
      total_duration_ms=235000,    # 最后一行的 end - 第一行的 start
      avg_line_duration_ms=5595,
      has_byword=True,
      has_reference_lines=True,
      metadata_keys=['ti', 'ar', 'al'],
      format='Enhanced LRC',       # 自动检测
  )
  ```

  方便用户快速了解歌词结构，也可用于 CI 校验。

- **[NEW-DETECT] LRC 格式自动检测**
  判断文件属于 Simple LRC / Enhanced LRC (逐字) / SPL，并在 `Lyrics` 上暴露：

  ```python
  >>> lyrics.format_type
  'Enhanced LRC'
  ```

  检测逻辑: 检查是否存在 `<mm:ss.xxx>` 逐字标签、是否包含 metadata 等。

### 🟢 低优先级

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

- **[NEW-INTERP] 时间插值填充**
  对于 `fill_implicit_line_end=True` 的扩展：不仅填充 `line.end`，还能对缺失 `word.start`/`word.end` 的逐字行做均匀插值。例如一行有 5 个字，已知 `line.start=1000` 和 `line.end=2000`，每个字自动分配 200ms。
  > 实现复杂度中等，场景有限，低优先级。

- **[NEW-OFFSET-META] `apply_delta` 自动清理 `metadata.offset`**
  README 提示用户"记得手动清理"——可添加 `clean_metadata_offset: bool = True` 参数使其成为内置行为。
  > 原作者标记为 "Closed as not planned"，重新提出供参考。

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

- **[NEW-ASYNC] 异步 I/O 支持**

  ```python
  lyrics = await Lyrics.aloads(lrc_text)
  lyrics = await Lyrics.aload(fp)
  ```

  对异步 Web 框架 (FastAPI 等) 友好，但纯 CPU 解析本质上是同步的，主要是文件 I/O 部分可异步化。

---

## 五、优先级汇总

| 优先级 | 编号 | 简述 |
|--------|------|------|
| 🔴 高 | B2 | `format_timetag` 精度丢失文档标注 |
| 🔴 高 | F-IO | 文件 I/O `load(fp)` / `dump(fp)` |
| 🔴 高 | F-REPR | 自定义 `__repr__` |
| 🔴 高 | F-DICT | `to_dict()` / `from_dict()` / `to_json()` |
| 🔴 高 | F-SRT | 导出 SRT 字幕格式 |
| 🔴 高 | F-STRICT | 解析严格模式 |
| 🔴 高 | F-DURATION | `LyricLine.duration` 属性 |
| 🔴 高 | F-RANGE | `Lyrics.lines_in_range()` 时间范围查询 |
| 🟡 中 | B5 | `LyricLine.start` 不允许 `None` + unsynced_lines |
| 🟡 中 | F-MUTATE | `Lyrics` 安全变更方法 |
| 🟡 中 | F-WEBVTT | 导出 WebVTT 格式 |
| 🟡 中 | F-COMBINE-ALL | 批量合并 `combine_all` |
| 🟡 中 | F-CONTAINS | `__contains__` 增强 |
| 🟡 中 | F-VALIDATE | `Lyrics.validate()` 一致性验证 |
| 🟡 中 | NEW-ERROR-LINE | 解析错误附带行号 |
| 🟡 中 | NEW-STATS | `Lyrics.stats()` 统计信息 |
| 🟡 中 | NEW-DETECT | LRC 格式自动检测 |
| 🟢 低 | B7 | 逐字时间戳与行范围一致性校验 |
| 🟢 低 | F-META-TYPE | Metadata 值类型辅助 |
| 🟢 低 | F-COPY | `Lyrics.copy()` |
| 🟢 低 | F-META-KEY | meta key 可配置字符集 |
| 🟢 低 | F-EXPORT-OTHER | 导出 ASS 等其他字幕格式 |
| 🟢 低 | F-LOGGING | `warnings.warn` 审计 |
| 🟢 低 | NEW-ROUNDTRIP | 轮转一致性保证 |
| 🟢 低 | NEW-SEARCH | 全文搜索 `Lyrics.search()` |
| 🟢 低 | NEW-UNSYNCED | 未同步行收集 |
| 🟢 低 | NEW-INTERP | 逐字时间插值填充 |
| 🟢 低 | NEW-OFFSET-META | `apply_delta` 自动清理 metadata.offset |
| 🟢 低 | NEW-CLI | CLI 入口 |
| 🟢 低 | NEW-ASYNC | 异步 I/O 支持 |
| ⚪ 观望 | MF-DUET | Walaoke 对唱扩展 |
| ⚪ 观望 | MF-COMMENT | 元数据注释 `[#...]` |
| ⚪ 观望 | MF-FUZZY | 模糊匹配合并 |
