# `[offset:]` 的正负语义

| 出处 | 说法 |
| --- | --- |
| [LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_%28file_format%29) | "global offset value for the lyric times, in milliseconds … with + causing lyrics to appear sooner" |
| [MobileRead Wiki](https://wiki.mobileread.com/wiki/LRC) | "a positive value causes lyrics to appear sooner" |
| [KDE Elisa !631](https://invent.kde.org/multimedia/elisa/-/merge_requests/631/diffs) | 原实现是正值让歌词更晚，与 Wikipedia 相反，单独提 MR 修正 |
| [Lyricify `OffsetHelper`](https://deepwiki.com/WXRIW/Lyricify-Lyrics-Helper/7.3-offset-and-type-helpers) | `line.StartTime -= offset`，正值让时间戳变小 |
| [Poweramp 论坛](https://forum.powerampapp.com/topic/26289-offset-value-in-lrc-files-and-embedded-synced-lyrics-is-not-respected/) | 有播放器完全不应用 offset |

结论：

- `[offset: +N]` 的含义是歌词整体提前 N 毫秒，即时间戳 `-= N`。
- 本库的 `apply_delta(ms)` 是时间戳 `+= ms`，正数让歌词更晚，符号与 `offset`
  相反。从 metadata 应用 offset 要取负号：

  ```python
  offset = int(lyrics.metadata.get("offset", 0))
  shifted = lyrics.apply_delta(-offset)
  ```

- 本库不自动应用 offset。换算关系由
  `tests/test_offset.py::TestLrcOffsetConvention` 固定。
