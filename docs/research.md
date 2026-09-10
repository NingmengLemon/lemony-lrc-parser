# Research（LRC 现状调研与语料数据）

本文件的结论都带出处：LRC 没有官方规范，很多"常识"其实是各实现自己定的，
决策前先去翻一遍真实实现与真实文件。

## 真实语料基线（只读审计）

对 6536 份与音频同名的 `.lrc`（33 万行，全部 UTF-8）跑过一遍：

| 指标 | 数值 |
| --- | --- |
| 解析异常 / `validate()` 问题 / 往返不变量违例 | 0 / 0 / 0 |
| 含 metadata 的文件 | 410（`by` 388、`ti` 32、`ar` 29、`al` 22、`offset` 12、其它 `re`/`ve`/`ly`/`mu`/`total`/`length`/`tool` 各 1） |
| 逐字行 / 带尖括号标签的文件 | 1666 行 / 71 个文件 |
| 空正文占位行 | 27023（8.2%） |
| 首词元晚于行首的行（`use_bracket_for_byword_tag=True` 会重复的行） | 296 |
| 相邻时间标签"相等" / "递减" | 1917 / 0 |
| 行首重复（完全相同）标签 | 0 |
| 时间标签尾数位数 | 3 位 547427、2 位 39266 |
| 与源文件字节不同（CRLF→LF、2 位尾数→3 位、行间空行） | 6536（100%） |

读法：

- 第 1 行说明当前实现与这份语料完全兼容；审计在改动前后各跑一遍，结果一致。
- 最后一行是 `NEW-PRESERVE-STYLE` 的动机：库能正确解析这些文件，但"写回"时会统一
  成自己的风格（100% 的文件都会变）。
- "相邻相等 1917 / 递减 0" 是"相等标签只记 debug、递减才告警"这条取舍的依据。
- "首词元晚于行首 296 行"说明 `use_bracket_for_byword_tag=True` 在真实数据上确实
  会让行数翻倍，而不是理论问题。

## 术语与 ID 标签标准集

社区整理（[LRC 文件格式](https://github.com/TriM-Organization/Lyric/blob/master/docs/Lrc%E6%96%87%E4%BB%B6%E6%A0%BC%E5%BC%8F.md)）
给出的标准 ID 标签是：

```
[ar:演唱者] [al:专辑] [ti:标题] [au:歌词作者] [length:长度]
[by:LRC 制作者] [re:制作者程序] [ve:程序版本] [offset:时间补偿(ms)]
```

这些正是 `MetadataKey` / `COMMON_METADATA_KEYS` 的取值来源。真实文件里还会出现
非标准 key（本次语料的 `ly` / `mu` / `total` / `tool`），所以库只做类型提示、
不做校验。

## metadata 语法

**value 能不能含 `]`？社区没有共识。**

| 实现 | 行为 |
| --- | --- |
| [FFmpeg `libavformat/lrcdec.c`](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/lrcdec.c) | `strchr(line.str, ']')` 取**第一个** `]` 收尾 → `[al: Album [Deluxe]]` 变成 `Album [Deluxe`（截断） |
| [rmpc#519](https://github.com/mierak/rmpc/issues/519) | 用户文件里真的这么写：`[title: Song Name [Explicit]]`，同时正文里还有 `[Drum Solo]` |
| 本库（0.4.0） | value 的边界 = **配对方括号**中深度首次归零的那个 `]`，于是 `Album [Deluxe]` 原样保留；不平衡时整行按正文处理 |

**为什么不用反斜杠转义？** [AMLL 的格式文档](https://amll.dev/en/guides/lyric/formats)
对同类问题（正文里的 `<`/`>`）写得很直白："转义没有官方标准；未匹配的一律当普通
文本"。对 metadata 同理：引入 `\]` 会自造方言（别的播放器会把 `\` 显示出来）、
破坏含反斜杠的既有 value、并让写出的文件不再是同一种格式。结论与替代方案见
[risks.md 的「已关闭 / 不计划」](risks.md#已关闭--不计划)。

## 重复 key 与"类 headers"容器设计

LRC 里 `[ti: a]` 出现两次是合法的（真实文件里少见但存在，例如同一文件里既写
`[ti: 标题]` 又写 `[ti: 标题 (Live)]`）。当前 `dict[str, str]` 会**静默丢掉前面的
值**，`list[tuple[str, str]]` 则能保真但丢掉 dict 的易用性。做决定前先看 HTTP 头
这类"同名可重复"的成熟容器是怎么设计的：

| 实现 | 形态 | 关键 API |
| --- | --- | --- |
| [werkzeug `Headers`](https://werkzeug.palletsprojects.com/en/stable/datastructures/) | "dict-like interface, but is **ordered**, can **store the same key multiple times**, and **iterating yields `(key,value)` pairs**" | `getlist()` / `get_all()` / `add()`（追加）/ `set()`（替换）/ `setlist()` / `extend()` |
| `httpx.Headers` | 有序、可重复 | `get_list(name)` / `multi_items()`；`__getitem__` 返回逗号拼接值 |
| `aiohttp` / `multidict.CIMultiDict` | 有序、可重复 | `getall()` / `add()` / `extend()` |
| `urllib3.HTTPHeaderDict` | 有序、可重复 | `getlist()` / `add()` |
| `requests.CaseInsensitiveDict` | 单值（后者覆盖） | 已知限制，社区讨论过改用 `HTTPHeaderDict`（[psf/requests#5498](https://github.com/psf/requests/issues/5498)） |

结论（三个相邻方案的取法）：

1. **推荐**：`metadata` 从 `dict[str, str]` 换成**有序 multimap**（`Metadata`），
   保留 dict 式读取（`meta["ti"]` 取第一个/最后一个）+ 新增 `getlist()` /
   `items()`（返回**全部** `(key, value)`，这是 dict 做不到的）+ `add` / `set`。
   这既满足"保真"，又不牺牲易用性，且与 werkzeug/httpx 的既有认知一致。
2. `list[tuple[str, str]]` 作为**序列化形态**是合理的（无损、JSON 友好），
   但作为**主 API** 不合适：会丢掉 `meta["ti"]`、`.copy()` / `.update()` 等
   直觉操作，用户得自己写查找。
3. `dict` 保持为"有损但方便"的出口（`to_dict()`），另给 `to_pairs()` 做无损导出。

因为这是破坏性变更，落在 0.5.0：见 [roadmap.md](roadmap.md) 的 `F-META-MULTI`。

## offset 标签的正负语义

社区文档与真实实现的说法如下：

| 出处 | 说法 |
| --- | --- |
| [LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_%28file_format%29) | "global offset value for the lyric times, in milliseconds … with **+ causing lyrics to appear sooner**" |
| [MobileRead Wiki](https://wiki.mobileread.com/wiki/LRC) | "+ shifts time up, - shifts down i.e. **a positive value causes lyrics to appear sooner**" |
| [KDE Elisa !631](https://invent.kde.org/multimedia/elisa/-/merge_requests/631/diffs) | 修的就是这个：他们原来做成"正值让歌词更晚"，与 Wikipedia 相反，被单独提 MR 修掉 |
| [Lyricify `OffsetHelper`](https://deepwiki.com/WXRIW/Lyricify-Lyrics-Helper/7.3-offset-and-type-helpers) | `line.StartTime -= offset` → 正值让时间戳变小，即歌词提前 |
| [Poweramp 论坛](https://forum.powerampapp.com/topic/26289-offset-value-in-lrc-files-and-embedded-synced-lyrics-is-not-respected/) | 有播放器**根本不应用** offset |

结论：

- `[offset: +N]` 的**目的语义**是"歌词整体提前 N 毫秒"，即时间戳 `-= N`。
- 本库的 `apply_delta(ms)` 是"时间戳 `+= ms`"（正数 = 更晚），符号与 LRC 的
  `offset` **相反**。所以从 metadata 应用 offset 的正确写法是：

  ```python
  offset = int(lyrics.metadata.get("offset", 0))
  shifted = lyrics.apply_delta(-offset)  # 正 offset → 歌词提前
  ```

- 本库**不自动**应用 offset（显式优于隐式），但上面的换算关系已经固化成测试，
  见 `tests/test_offset.py::TestLrcOffsetConvention`。

## 时间标签的宽松形式

同一份社区整理列出了这些被真实文件使用的写法（本库全部接受）：

```
[mm:ss.fff]  [mm:ss.xx]  [hh:mm:ss]  [hh:mm:ss.fff]  [hh:mm:ss.xx]  [mm:ss]
[mm:ss.xx][mm:ss.xx][mm:ss.xx]重复出现的歌词
```

本库的策略：尾数 1–6 位都收（按位数补齐/截断到毫秒）、分钟 1–4 位、秒数越界
（`[00:99.000]`）按字面折算并 warning、行内空白容忍。语料统计显示实际只出现
2 位（39266）与 3 位（547427）两种。

## typing-extensions 下限实测

本库只从 `typing_extensions` 取两个符号：`Self`（4.0+）与 `override`（4.4+），
但"下限 = 4.4.0"只在旧解释器上成立。逐版本实测（每个组合都跑完整测试套件）：

| Python | 4.4.0 | 4.5.0 | 4.6.0 | 4.10.0 | 4.12.2 | 4.13.0 | 4.14.0 | 可用下限 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3.9 / 3.10 / 3.11 | ✅ | — | — | — | — | — | — | **4.4.0** |
| 3.12 / 3.13 / 3.14 | ❌ | ❌ | ✅ | — | — | — | — | **4.6.0** |
| 3.15（3.15.0rc1） | ❌ | — | ✅ | ❌ | ❌ | ❌ | ✅ | **4.14.0** |

（4.3.0 及更早版本没有 `override`，直接 `ImportError`。）

两种失败模式：

- 3.12–3.14 + 4.4/4.5：`TypeError: type 'typing.TypeVar' is not an acceptable base type`
  ——老版本 typing-extensions 不认识新解释器的 typing 内部结构；
- 3.15 + 4.10–4.13：`AttributeError: module 'typing' has no attribute …`
  ——中间几个版本引用了 3.15 里已改名/移除的属性，到 4.14.0 才修好。

**3.15 那一档是"区间断裂"而非"下限更高"**：4.6.0 其实能跑通，但 4.10–4.13 会炸，
所以不能写成 `>=4.6.0`（那样会放进断裂区间），只能写 `>=4.14.0`。
pyproject 的分档写法与 CI 的"最低 typing-extensions"矩阵作业都基于这张表
（3.15 解释器正式可用后再把那一档加进矩阵）。

## 参考资料

- [LRC 文件格式（社区整理）](https://github.com/TriM-Organization/Lyric/blob/master/docs/Lrc%E6%96%87%E4%BB%B6%E6%A0%BC%E5%BC%8F.md)
  —— ID 标签标准集、时间标签的各种写法。
- [Lyric Formats | AMLL Docs](https://amll.dev/en/guides/lyric/formats)
  —— LRC / LRC A2 / YRC / QRC 的差异，以及"转义未标准化"的说明。
- [FFmpeg `libavformat/lrcdec.c`](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/lrcdec.c)
  —— 事实参考实现：metadata 取第一个 `]` 收尾、key 只认小写字母开头。
- [LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_%28file_format%29)、
  [MobileRead Wiki: LRC](https://wiki.mobileread.com/wiki/LRC)
  —— `offset` 等 ID 标签的语义描述。
- [KDE Elisa !631](https://invent.kde.org/multimedia/elisa/-/merge_requests/631/diffs)、
  [Lyricify Lyrics Helper](https://deepwiki.com/WXRIW/Lyricify-Lyrics-Helper/7.3-offset-and-type-helpers)
  —— offset 的实际实现（含一次符号修正）。
- [rmpc#519](https://github.com/mierak/rmpc/issues/519)
  —— 真实用户文件里同时存在 `[title: Song Name [Explicit]]` 与正文中的
  `[Drum Solo]`。
- [werkzeug Data Structures](https://werkzeug.palletsprojects.com/en/stable/datastructures/)、
  [psf/requests#5498](https://github.com/psf/requests/issues/5498)
  —— 同名可重复容器的设计参考。
- [SPL Specification](https://moriafly.com/standards/spl.html)
