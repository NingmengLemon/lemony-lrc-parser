"""lemony-lrc-parser —— 简洁的 Python LRC 歌词解析器.

公共 API 分成三层：

1. **面向对象入口**（推荐）：:class:`Lyrics` 及其 :meth:`~Lyrics.loads` /
   :meth:`~Lyrics.dumps` 方法。

   .. code-block:: python

       from lemony_lrc_parser import Lyrics

       lyrics = Lyrics.loads(lrc_text)
       for line in lyrics:
           print(line.start, line.text)
       lrc_out = lyrics.dumps()

2. **顶层便捷函数**（等价于 :class:`Lyrics` 的方法）：:func:`loads` /
   :func:`dumps`，风格对齐 ``json`` / ``pickle``。

   .. code-block:: python

       import lemony_lrc_parser as llp

       lyrics = llp.loads(lrc_text)
       out = llp.dumps(lyrics)

3. **底层函数与工具**：:func:`parse_lrc` / :func:`parse_line` / :func:`dump_lrc`
   以及时间标签工具 :func:`format_timetag` / :func:`parse_timetag`。
"""

from __future__ import annotations

from typing import Any

from .exceptions import InvalidLyricsError, LyricsParserError
from .models import BasicLyricLine, LyricLine, Lyrics, LyricWord
from .parser import parse_line, parse_lrc
from .serializer import dump_lrc
from .timetag import format_timetag, parse_timetag

__all__ = [
    # --- 数据模型 ---
    "BasicLyricLine",
    "LyricLine",
    "LyricWord",
    "Lyrics",
    # --- 异常 ---
    "InvalidLyricsError",
    "LyricsParserError",
    # --- 主 API（推荐）---
    "dumps",
    "loads",
    # --- 低层 API ---
    "dump_lrc",
    "parse_line",
    "parse_lrc",
    # --- 时间标签工具 ---
    "format_timetag",
    "parse_timetag",
]


def loads(s: str, *, fill_implicit_line_end: bool = False) -> Lyrics:
    """从 LRC 字符串解析出一份 :class:`Lyrics`.

    等价于 :meth:`Lyrics.loads`。
    """
    return Lyrics.loads(s, fill_implicit_line_end=fill_implicit_line_end)


def dumps(lyrics: Lyrics, **kwargs: Any) -> str:
    """把 :class:`Lyrics` 序列化为 LRC 字符串.

    等价于 ``lyrics.dumps(**kwargs)``；支持的关键字参数见
    :meth:`Lyrics.dumps`。
    """
    return lyrics.dumps(**kwargs)
