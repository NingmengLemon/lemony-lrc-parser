# Feature Ideas for lemony-lrc-parser

本文档记录对项目的功能增强建议, 按优先级排序。

> 大部分是 AI 写的, 但是窝有在审,,

> 哎呀阿米诺, 很多问题就是 lrc 没标准化导致的, 看看隔壁 srt / webvtt / ass ,,

---

## 设计缺陷 / 逻辑漏洞 / 非预期行为

### ✅ B1. 仅含逐字标签 (尖括号) 的行被误判为参考行

[`parser.py:_split_leading_line_timetags`](src/lemony_lrc_parser/parser.py:289) 只匹配 `LINE_TIMETAG_REGEX` (方括号 `[...]`)。当一行以 `<00:01.000>text` 开头 (没有行级方括号标签) 时:

1. `parse_lrc` 中 `word_tag_check.match()` 命中, 进入歌词行分支
2. `_split_leading_line_timetags` 剥离不到任何标签 → `time_tags=[]`
3. 该行落入 `if not time_tags` 分支 → 若 `last_tag` 存在则成为**参考行**, 否则被当作孤儿行丢弃

**预期行为**: 纯逐字标签行应该是合法的 Enhanced LRC 歌词行, 行首第一个逐字标签的 start 应当作 `line.start`。

> 赞同以尖括号开头的应该当作 line.start, 不过开头要是连这个都没有的话真该丢了

### B2. `format_timetag` 在 `tail_digits < 3` 时存在精度丢失

[`timetag.py:format_timetag`](src/lemony_lrc_parser/timetag.py:55) 中:

```python
tail = millis // 10 ** (3 - tail_digits)  # 555ms → 55 (百分秒)
```

格式化后 `55` → 解析时 `_match_to_ms` 补齐到 3 位 → `"550"` → **550ms**, 丢失 5ms。

虽然默认值 `tail_digits=2` 是故意为之 (输出百分秒), 但用户可能误以为这是无损操作。建议在文档中明确标注此为**有损截断**, 或在 `tail_digits < 3` 时发出 warning。

> 文档问题, 不用改实现. 实际上Wikipedia之类的参考网站以及从网易云音乐/QQ音乐等平台抓取的lrc文件的精度都只到百分秒.
> 顺便, tail_digits>3的情况其实没有意义,, 因为内部精度只到毫秒, 继续往小单位精确的话不仅人类没有感知, 还会对同时间戳参考行的判断造成困难.

### ✅ B3. `_format_words` 对参考行错误传入主行的 `line_end`

[`serializer.py:_format_words`](src/lemony_lrc_parser/serializer.py:86) 在格式化参考行时传入了 `line_end=line.end` (主行的结束时间):

```python
buffer.write(
    _format_words(
        refline,
        line_start=line_start,
        line_end=line.end,       # ← 应传 None 或参考行自身的结束时间
        ...
    )
)
```

这会导致: 若参考行最后一个词元的 `end` 恰好等于主行 `line.end`, 该词元的结束标签会被错误省略 (因为 `_format_words` 的逻辑是"若与 line_end 相同则省略, 因为调用方会输出行尾标签")。但参考行**没有**独立的行尾标签输出, 所以这个省略是错误的。

> 修

### ✅ B4. `parse_timetag` 使用严格正则, 与解析器的宽松正则不一致

[`timetag.py:parse_timetag`](src/lemony_lrc_parser/timetag.py:72) 使用 `TIMETAG_REGEX_STRICT` (要求 `mm:ss.xxx` 三段齐全、毫秒 1-3 位、无空白), 而 `parse_lrc` 内部使用 `LINE_TIMETAG_REGEX` (允许 1-6 位毫秒可选、允许空白)。

结果: `parse_timetag("[00:05]")` 返回 `None`, 但 `parse_lrc` 可以解析 `[00:05]text`。公共 API 与内部行为不一致。

> 这个得修, 这个是之前写的时候脑子抽风导致的
> 以及 strict timetag 除了 parse_timetag 实际上都没用到过, parse_timetag 除了导出内部也没用过, 而我们库其实目前根本没用户, 气笑了

### B5. `LyricLine.start` 允许 `None`, 但语义上 synced lyrics 不应存在无时间戳行

[`models.py:LyricLine`](src/lemony_lrc_parser/models.py:106) 的 `start: int | None = None`。当前代码在多处静默处理:

- [`combine`](src/lemony_lrc_parser/models.py:176) 发 warning 后跳过
- [`dump_lrc`](src/lemony_lrc_parser/serializer.py:45) 发 warning 后跳过
- [`apply_delta`](src/lemony_lrc_parser/offset.py:24) 用 `if line.start is not None` 守卫

对于 synced LRC, `start=None` 的行在语义上不成立。建议要么在解析阶段就拒绝这种行 (strict mode), 要么在模型层明确区分 "synced line" 和 "unsynced line"。

> 我们的库面向的就是 synced lyrics,,, 或许可以把 unsynced 单独收集起来和 synced 分开, 比如写到 lyrics 的另一个新成员 `unsynced_lines: list[str]`, 而不是 drop 掉. 同时让 LyricLine.start 不允许为 None.
> 那么遇到又没有 start, 内部又有词级标签的怎么办呢?
> ... 啥比吧, 气笑了, 直接原样滚到 unsynced 里去

### B6. `combine` 排序时 `line.start or 0` 的隐式 fallback

[`models.py:combine`](src/lemony_lrc_parser/models.py:199):

```python
new.lines = sorted(pool.values(), key=lambda line: line.start or 0)
```

虽然 `start=None` 的行已在上文被过滤, 但 `or 0` 是一个隐蔽的 fallback——如果将来有 None 漏过, 它会被静默排到最前面而不会报错。

> 这个 or 0 是给类型系统的兜底, 如其他地方所示, synced lyrics 不应存在无时间戳行

### B7. 缺少逐字时间戳与行时间范围的一致性校验

当前没有任何代码检查 `LyricToken.start` / `LyricToken.end` 是否落在所属 `LyricLine.start` ~ `LyricLine.end` 范围内。恶意或损坏的 LRC 文件可能产生 `word.start < line.start` 的数据, 而 `_register_line_at_tags` 只检查了第一个词的 start (且只发 warning)。

> 可以加, 但是优先级降低

---

## 补充 Feature 提案

### F1. `LyricLine.duration` 属性

```python
@property
def duration(self) -> int | None:
    if self.start is not None and self.end is not None:
        return self.end - self.start
    return None
```

### F2. 时间范围查询

```python
def lines_in_range(self, start_ms: int, end_ms: int) -> list[LyricLine]:
    """返回所有时间戳完全或部分落在 [start_ms, end_ms] 内的行."""
```

### F3. `Lyrics` 安全变更方法

当前直接操作 `lyrics.lines` 会绕过排序/一致性维护:

```python
lyrics.insert_line(line: LyricLine)   # 插入后自动排序
lyrics.remove_line(index: int)         # 安全删除
```

### F4. 解析严格模式 (`ParseOptions.strict: bool`)

开启后以下情况从 warning 升级为抛出 `InvalidLyricsError`:

- 行首没有时间标签的孤立行
- 时间标签不单调递增 (行级)
- `start=None` 的行
- metadata key 不符合标准格式
- 同一文件中有重复的 `[offset:...]` 标签

> 可以我喜欢这个

### F5. `Lyrics.to_dict()` / `Lyrics.from_dict()`

```python
lyrics.to_dict()  # → dict 可 JSON 序列化, 用于 API 传输
Lyrics.from_dict(d)  # ← 从 dict 还原
```

(属于 #4 "导出为其他格式" 的子项, 建议提升优先级)

> 提优先级

### F6. Metadata 值类型辅助

```python
lyrics.get_metadata_int("offset")    # → int | None
lyrics.get_metadata_float("offset")  # → float | None
```

当前 `offset` 存储为字符串 `"500"`, 每次用都要手动 `int()`。

> 减低优先级, 手动 int() 怎么你了 ()

### F7. 批量合并 (`combine` 接受多个 `Lyrics`)

```python
main.combine_all([trans_zh, trans_ja, translit])
# 等价于 main + trans_zh + trans_ja + translit
```

> 可以有, 虽然链式 `+` 好像也能做到 (?)

### F8. `__contains__` 增强

如文档原有提议, 支持:

- `"word" in token` → `"word" in token.content`
- `"substring" in line` → `"substring" in line.text`
- `"substring" in lyrics` → `any("substring" in line.text for line in lyrics)`

`BasicLyricLine` 可以是 `list` 的子类以支持 `token in line.content`。

---

## 高优先级

### 1. 文件 I/O (`Lyrics.load(path)` / `lyrics.dump(path)`)

对标 `json.load` / `json.dump`, 支持从文件路径直接读写:

```python
# 读取
lyrics = Lyrics.load("song.lrc")
lyrics = Lyrics.load("song.lrc", encoding="utf-8")

# 写入
lyrics.dump("song_offset.lrc")
```

`load` 内部打开文件、读取文本、调用 `loads`; `dump` 调用 `dumps` 后写入。

> 没记错的话 json 模块的 dump 和 load 是不支持传入路径的, 支持的是 file object, 应该与它对齐

### 2. 自定义 `__repr__` 改善调试体验

当前 `LyricToken` / `LyricLine` / `Lyrics` 依赖 dataclass 自动生成的 `__repr__`,
输出冗长难读。建议为各模型添加简洁的 `__repr__`:

```python
>>> token = LyricToken(content="hello", start=1000, end=2000)
>>> token
LyricToken(content='hello', start=1000, end=2000)  # 当前 dataclass 默认

>>> line = LyricLine(start=1000, content=[token])
>>> line
LyricLine(start=1000, text='hello', words=1)        # 建议
```

`Lyrics` 可显示 `Lyrics(lines=42, metadata_keys=['ti', 'ar', 'al'])`。

## 中优先级

### 3. `apply_delta` 自动清理 metadata offset

当 `Lyrics.apply_delta(ms)` 被调用、且 `metadata["offset"]` 存在时,
可选择自动移除或更新该键。当前 README 提示用户"记得手动清理"——可做成内置行为。

```python
# 添加参数 clean_metadata_offset: bool = True
shifted = lyrics.apply_delta(500, clean_metadata_offset=True)
# shifted.metadata 中不再含 "offset"
```

> Closed as not planned.

### 4. 导出为其他格式

提供 `Lyrics` → JSON / SRT / ASS 的转换方法或工具函数:

```python
lyrics.to_json()      # JSON 结构化输出
lyrics.to_srt()       # SubRip 字幕格式
```

适用场景: 将歌词用于视频字幕制作。

> 别忘了 webvtt

>> to_json, 或者说, 与字典互转, 和 to_srt 是高优先级, 其他格式是低优先级

### 5. 为 `combine` 添加 `skip_orphan` 选项

当前 `combine` 对 `start=None` 的行只发 warning 后静默丢弃,
没提供类似 `other_as_refline_only` 的选项来控制行为。

> Closed as intended.

>> 实际上 line 的 start 不应该为 None. 这才是应该修的, 因为 synced lyrics 里不应该有孤立的歌词行.

## 低优先级

### 6. `Lyrics.copy()` 方法

`deepcopy` 的便捷封装, 语义更清晰:

```python
def copy(self) -> Lyrics:
    from copy import deepcopy
    return deepcopy(self)
```

### 7. 数据一致性验证 API

提供 `lyrics.validate()` 方法, 检查:

- 时间戳是否严格递增
- 没有 `start is None` 的行（synced LRC 不应出现）
- 逐字标签的时间是否在行时间范围内
- metadata key 是否合法

返回 `list[ValidationError]` 或抛异常。

### 8. METATAG key 支持更宽泛的字符集

当前 `METATAG_REGEX` 限制 key 为 `[a-zA-Z][a-zA-Z0-9]{1,15}`,
不支持下划线 (`_`)、连字符 (`-`)。一些非标准 LRC 变体可能使用这些字符。

建议改为 `[a-zA-Z][a-zA-Z0-9_-]{0,31}` 或提供 `meta_key_pattern` 选项。

> 真的有可能吗,, 可配置的 meta_key_pattern 倒是可以

## 未分类优先级

### contains dunder 方法

让 Token, Line, Lyrics 支持 `"string" in obj`

难点是 line 中的子串可能来自多个 token

为此, 应该让 BasicLyricLine 为继承自 list 的类以实现更多方法

### 一些地方的 logger.warning 换成 warnings.warn

一些地方用 logger.warning 警告力度可能不够, 酌情考虑

### "对唱" feature

来自 Wikipedia, "Walaoke扩展", 原文如下:

The Walaoke extension, available only in Walaoke from Walasoft, allows the specification of parts for a male-female duet. This is done through the use of M: , F: , and D: at the start of a line for male, female, and duet lines respectively. This allows them to be displayed in different colours. This is illustrated with an example below.

```lrc
[00:12.00]Line 1 lyrics
[00:17.20]F: Line 2 lyrics
[00:21.10]M: Line 3 lyrics
[00:24.00]Line 4 lyrics
[00:28.25]D: Line 5 lyrics
[00:29.02]Line 6 lyrics
```

在现实中完全没见到过, 最低优先级. 或者 Closed as not planned.

### 元数据中的注释

来自 Wikipedia, 核心格式中, tag type 可能为 `#`, 表示元数据标签中的 value 为注释

以及如果出现多个注释会只保留最后一个, 按照直觉注释应该会可能有多个, 与现有实现方式 `dict[key, value]` 冲突

在现实中完全没见到过,,
