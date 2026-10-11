# metadata

## 标准 ID 标签

社区整理的 [LRC 文件格式](https://github.com/TriM-Organization/Lyric/blob/master/docs/Lrc%E6%96%87%E4%BB%B6%E6%A0%BC%E5%BC%8F.md)
列出的标准标签：

```text
[ar:演唱者] [al:专辑] [ti:标题] [au:歌词作者] [length:长度]
[by:LRC 制作者] [re:制作者程序] [ve:程序版本] [offset:时间补偿(ms)]
```

这是 `MetadataKey` / `COMMON_METADATA_KEYS` 的取值来源。真实文件里还有非标准
key，所以库只做类型提示，不校验。

## value 能不能含 `]`

社区没有共识。

| 实现 | 行为 |
| --- | --- |
| [FFmpeg `lrcdec.c`](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/lrcdec.c) | `strchr(line.str, ']')` 取第一个 `]` 收尾，`[al: Album [Deluxe]]` 截断成 `Album [Deluxe`；key 只认小写字母开头 |
| [rmpc#519](https://github.com/mierak/rmpc/issues/519) | 用户文件里就是 `[title: Song Name [Explicit]]`，正文里同时还有 `[Drum Solo]` |
| 本库 | 配对方括号中深度首次归零的那个 `]` 收尾；不平衡时整行按正文处理 |

[AMLL 的格式文档](https://amll.dev/en/guides/lyric/formats) 对正文里的 `<` / `>`
写明"转义没有官方标准，未匹配的一律当普通文本"，metadata 同理，所以不引入转义
（[不计划](../design/not-planned.md)）。

## 同名 key 与容器形态

`[ti: a]` 出现两次是合法的，真实文件里少见但存在（同一文件既写
`[ti: 标题]` 又写 `[ti: 标题 (Live)]`）。裸 `dict` 会静默丢掉前面的值，
`list[tuple[str, str]]` 保真但丢掉 dict 的易用性。HTTP 头这类同名可重复的成熟
容器走的是第三条路：

| 实现 | 形态 | 关键 API |
| --- | --- | --- |
| [werkzeug `Headers`](https://werkzeug.palletsprojects.com/en/stable/datastructures/) | 有序、可重复，迭代给 `(key, value)` | `getlist()` / `add()` / `set()` / `setlist()` / `extend()` |
| `httpx.Headers` | 有序、可重复 | `get_list()` / `multi_items()`；`__getitem__` 返回逗号拼接值 |
| `multidict.CIMultiDict` | 有序、可重复 | `getall()` / `add()` / `extend()` |
| `urllib3.HTTPHeaderDict` | 有序、可重复 | `getlist()` / `add()` |
| `requests.CaseInsensitiveDict` | 单值，后者覆盖 | 已知限制，见 [psf/requests#5498](https://github.com/psf/requests/issues/5498) |

结论：

1. 主 API 用有序 multimap，保留 dict 式读取，另加 `getlist()`、返回全部条目的
   `items()`、`add` / `set`。与 werkzeug / httpx 的既有认知一致。
2. `list[tuple[str, str]]` 适合当序列化形态（无损、JSON 友好），即 `to_pairs()`，
   不适合当主 API。
3. `dict` 保留为有损但方便的出口，即 `to_dict()`。

`meta["ti"]` 取最后一次出现的值，与裸 dict 的行为一致，升级后既有代码读到的值
不变。落地后的口径见 [semantics.md](../design/semantics.md#metadata)。
