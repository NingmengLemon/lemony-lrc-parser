"""lemony-lrc-parser —— 简洁的 Python LRC 歌词解析器.

公共 API 分成三层:

1. **面向对象入口** (推荐) : :class:`Lyrics` 及其 :meth:`~Lyrics.loads` /
   :meth:`~Lyrics.dumps` 方法.

   .. code-block:: python

       from lemony_lrc_parser import Lyrics

       lyrics = Lyrics.loads(lrc_text)
       for line in lyrics:
           print(line.start, line.text)
       lrc_out = lyrics.dumps()

2. **顶层便捷函数** (等价于 :class:`Lyrics` 的方法) : :func:`loads` /
   :func:`dumps`, 风格对齐 ``json`` / ``pickle``.

   .. code-block:: python

       import lemony_lrc_parser as llp

       lyrics = llp.loads(lrc_text)
       out = llp.dumps(lyrics)

3. **底层函数与工具**: :func:`parse_lrc` / :func:`parse_line`
    以及时间标签工具 :func:`format_timetag` / :func:`parse_timetag`.
"""

from __future__ import annotations

from typing import TextIO

from .exceptions import (
    InvalidLyricsError,
    LyricsParserError,
    ProgrammingError,
    TimestampUnderflowError,
)
from .models import (
    BasicLyricLine,
    LyricLine,
    LyricLineDict,
    Lyrics,
    LyricsDict,
    LyricToken,
    LyricTokenDict,
    ParseOptions,
    SerializationOptions,
    SubtitleOptions,
)
from .parser import parse_line, parse_lrc
from .subtitle import dump_srt, dump_webvtt, parse_srt, parse_webvtt
from .timetag import format_timetag, parse_timetag
from .validation import (
    ValidationIssue,
    ValidationOptions,
    ValidationSeverity,
    validate_lyrics,
)

__all__ = [
    "BasicLyricLine",
    "LyricLine",
    "LyricToken",
    "Lyrics",
    "LyricTokenDict",
    "LyricLineDict",
    "LyricsDict",
    "InvalidLyricsError",
    "LyricsParserError",
    "ProgrammingError",
    "TimestampUnderflowError",
    "ParseOptions",
    "SerializationOptions",
    "SubtitleOptions",
    "ValidationIssue",
    "ValidationOptions",
    "ValidationSeverity",
    "validate_lyrics",
    "dumps",
    "loads",
    "dump",
    "load",
    "parse_line",
    "parse_lrc",
    "format_timetag",
    "parse_timetag",
    "dump_srt",
    "dump_webvtt",
    "parse_srt",
    "parse_webvtt",
]


def loads(s: str, *, options: ParseOptions | None = None) -> Lyrics:
    """从 LRC 字符串解析出一份 :class:`Lyrics`.

    等价于 :meth:`Lyrics.loads`.
    """
    return Lyrics.loads(s, options=options)


def dumps(lyrics: Lyrics, *, options: SerializationOptions | None = None) -> str:
    """把 :class:`Lyrics` 序列化为 LRC 字符串.

    等价于 ``lyrics.dumps(options=options)``
    """
    return lyrics.dumps(options=options)


def load(fp: TextIO, *, options: ParseOptions | None = None) -> Lyrics:
    """从文件加载 LRC 内容.

    等价于 :meth:`Lyrics.load`.
    """
    return Lyrics.load(fp, options=options)


def dump(
    lyrics: Lyrics, fp: TextIO, *, options: SerializationOptions | None = None
) -> None:
    """把 :class:`Lyrics` 保存到文件.

    等价于 :meth:`Lyrics.dump`
    """
    lyrics.dump(fp, options=options)
