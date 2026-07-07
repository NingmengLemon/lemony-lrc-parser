"""简单字幕格式 (SRT / WebVTT) 与 LRC 的互转.

本模块提供 :class:`.models.Lyrics` 与常见字幕格式之间的双向转换:

* :func:`dump_srt` / :func:`parse_srt` —— SubRip (``.srt``).
* :func:`dump_webvtt` / :func:`parse_webvtt` —— WebVTT (``.vtt``).

字幕格式与 LRC 的核心差异:

* 字幕以 **[start, end] 时间区间** 为单位, 而 LRC 以行首时间戳为主、
  行尾时间戳可选. 因此 LRC → 字幕时若某行缺少 ``end``, 会用下一行的
  ``start`` (或 :attr:`SubtitleOptions.default_duration_ms`) 补齐.
* 字幕的一条 cue 可包含多行文本. 转换时主行文本取
  :attr:`.models.LyricLine.text`, 参考行 (翻译/音译) 追加在其后;
  反向解析时, cue 的首行作为主行, 其余行作为参考行.
* 字幕不承载 LRC 的逐字标签与 metadata, 这些信息在导出时会被
  拍平/丢弃.
"""

from __future__ import annotations

import re
from io import StringIO
from logging import getLogger

from .exceptions import InvalidLyricsError
from .models import (
    BasicLyricLine,
    LyricLine,
    Lyrics,
    LyricToken,
    SubtitleOptions,
)

logger = getLogger(__name__)

__all__ = [
    "dump_srt",
    "dump_webvtt",
    "parse_srt",
    "parse_webvtt",
]

#: 匹配字幕时间戳 ``[HH:]MM:SS,mmm`` 或 ``[HH:]MM:SS.mmm``.
#: 小时段可选; 毫秒分隔符允许逗号 (SRT) 或点 (WebVTT).
_TS_REGEX = re.compile(
    r"""
    (?:(?P<h>\d+):)?
    (?P<m>\d{1,3})
    :
    (?P<s>\d{1,2})
    [.,]
    (?P<ms>\d{1,3})
    """,
    re.VERBOSE,
)

#: 匹配一条 cue 的时间轴行 ``start --> end`` (箭头两侧允许额外样式设置).
_CUE_TIMING_REGEX = re.compile(
    r"""
    ^\s*
    (?P<start>(?:\d+:)?\d{1,3}:\d{1,2}[.,]\d{1,3})
    \s*-->\s*
    (?P<end>(?:\d+:)?\d{1,3}:\d{1,2}[.,]\d{1,3})
    (?P<settings>.*)$
    """,
    re.VERBOSE,
)


def _format_ts(ms: int, *, sep: str) -> str:
    """把毫秒数格式化为 ``HH:MM:SS<sep>mmm`` 字幕时间戳.

    Args:
        ms: 毫秒时间戳 (不允许为负).
        sep: 毫秒分隔符, SRT 用 ``","``, WebVTT 用 ``"."``.
    """
    if ms < 0:
        raise InvalidLyricsError(f"Negative timestamp is not allowed: {ms}ms")
    hours = ms // 3_600_000
    minutes = (ms % 3_600_000) // 60_000
    seconds = (ms % 60_000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"


def _parse_ts(s: str) -> int:
    """把字幕时间戳字符串解析为毫秒数.

    支持 ``HH:MM:SS,mmm`` / ``HH:MM:SS.mmm`` / ``MM:SS.mmm`` 等形式.
    """
    match = _TS_REGEX.fullmatch(s.strip())
    if match is None:
        raise InvalidLyricsError(f"Invalid subtitle timestamp: {s!r}")
    hours = int(match["h"] or 0)
    minutes = int(match["m"])
    seconds = int(match["s"])
    tail = match["ms"]
    # 标准化毫秒到 3 位: "1" -> 100, "12" -> 120, "123456" -> 123
    if len(tail) > 3:
        tail = tail[:3]
    else:
        tail = tail.ljust(3, "0")
    millis = int(tail)
    return millis + seconds * 1000 + minutes * 60_000 + hours * 3_600_000


def _cue_texts(line: LyricLine, options: SubtitleOptions) -> list[str]:
    """收集一行歌词在字幕 cue 中应显示的文本行 (主行 + 可选参考行)."""
    texts: list[str] = []
    main = line.text
    if main:
        texts.append(main)
    if options.include_reference_lines:
        for refline in line.reference_lines:
            ref_text = refline.text
            if ref_text:
                texts.append(ref_text)
    if not texts:
        # 允许空文本 cue, 避免时间轴错位
        texts.append("")
    return texts


def _iter_cues(
    lyrics: Lyrics, options: SubtitleOptions
) -> list[tuple[int, int, list[str]]]:
    """把 :class:`Lyrics` 转换为 ``(start, end, text_lines)`` 三元组列表.

    缺失的行尾时间按以下顺序补齐:

    1. 若 :attr:`SubtitleOptions.fill_end_from_next` 为真且存在下一行,
       用下一行的 ``start``.
    2. 否则用 ``start + default_duration_ms``.

    补齐后仍非正的区间 (``end <= start``) 会被抬升为
    ``start + default_duration_ms``, 保证字幕时长有效.
    """
    lines = list(lyrics.lines)
    cues: list[tuple[int, int, list[str]]] = []
    for idx, line in enumerate(lines):
        start = line.start
        end = line.end
        if end is None:
            if options.fill_end_from_next and idx + 1 < len(lines):
                end = lines[idx + 1].start
            else:
                end = start + options.default_duration_ms
        if end <= start:
            end = start + options.default_duration_ms
        cues.append((start, end, _cue_texts(line, options)))
    return cues


def dump_srt(lyrics: Lyrics, *, options: SubtitleOptions | None = None) -> str:
    """把一份 :class:`Lyrics` 序列化为 SRT (SubRip) 字幕文本.

    Args:
        lyrics: 待转换的歌词对象.
        options: 转换选项, 见 :class:`.models.SubtitleOptions`.
    """
    options = options or SubtitleOptions()
    buffer = StringIO()
    for index, (start, end, texts) in enumerate(_iter_cues(lyrics, options), start=1):
        buffer.write(f"{index}\n")
        buffer.write(f"{_format_ts(start, sep=',')} --> {_format_ts(end, sep=',')}\n")
        buffer.write("\n".join(texts))
        buffer.write("\n\n")
    return buffer.getvalue()


def dump_webvtt(lyrics: Lyrics, *, options: SubtitleOptions | None = None) -> str:
    """把一份 :class:`Lyrics` 序列化为 WebVTT 字幕文本.

    Args:
        lyrics: 待转换的歌词对象.
        options: 转换选项, 见 :class:`.models.SubtitleOptions`.
    """
    options = options or SubtitleOptions()
    buffer = StringIO()
    buffer.write("WEBVTT\n\n")
    for start, end, texts in _iter_cues(lyrics, options):
        buffer.write(f"{_format_ts(start, sep='.')} --> {_format_ts(end, sep='.')}\n")
        buffer.write("\n".join(texts))
        buffer.write("\n\n")
    return buffer.getvalue()


def _split_blocks(text: str) -> list[list[str]]:
    """按空行把字幕文本切分为若干块, 每块是去掉行尾空白的字符串列表."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.strip() == "":
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(stripped)
    if current:
        blocks.append(current)
    return blocks


def _cue_block_to_line(block: list[str]) -> LyricLine | None:
    """把一个含时间轴的 cue 块转换为 :class:`LyricLine`.

    块内首行可能是数字序号 (SRT) 或 cue 标识 (WebVTT), 会被跳过;
    时间轴行之后的文本, 首行作为主行内容, 其余行作为参考行.
    不含时间轴的块返回 ``None``.
    """
    timing_idx: int | None = None
    timing_match: re.Match[str] | None = None
    for i, ln in enumerate(block):
        m = _CUE_TIMING_REGEX.match(ln)
        if m is not None:
            timing_idx = i
            timing_match = m
            break

    if timing_idx is None or timing_match is None:
        return None

    start = _parse_ts(timing_match["start"])
    end = _parse_ts(timing_match["end"])

    text_lines = [ln for ln in block[timing_idx + 1 :] if ln.strip() != ""]

    if text_lines:
        content = BasicLyricLine([LyricToken(content=text_lines[0])])
    else:
        content = BasicLyricLine([LyricToken(content="")])
    reference_lines = [BasicLyricLine([LyricToken(content=t)]) for t in text_lines[1:]]

    return LyricLine(
        start=start,
        end=end,
        content=content,
        reference_lines=reference_lines,
    )


def _parse_subtitle(text: str) -> Lyrics:
    """SRT / WebVTT 通用块解析: 提取所有 cue 块并按 ``start`` 排序."""
    lyrics = Lyrics()
    for block in _split_blocks(text):
        # 跳过 WebVTT 头部与 NOTE / STYLE / REGION 块
        head = block[0].strip()
        if head == "WEBVTT" or head.startswith("WEBVTT"):
            continue
        if head.startswith(("NOTE", "STYLE", "REGION")):
            continue
        line = _cue_block_to_line(block)
        if line is not None:
            lyrics.lines.append(line)
    lyrics.lines = sorted(lyrics.lines, key=lambda ln: ln.start)
    return lyrics


def parse_srt(text: str) -> Lyrics:
    """把 SRT (SubRip) 字幕文本解析为 :class:`Lyrics`.

    每条 cue 变成一行 :class:`LyricLine`, 携带 ``start`` / ``end`` 区间;
    多行 cue 文本的首行作为主行, 其余行作为参考行.
    """
    return _parse_subtitle(text)


def parse_webvtt(text: str) -> Lyrics:
    """把 WebVTT 字幕文本解析为 :class:`Lyrics`.

    行为与 :func:`parse_srt` 一致, 额外会跳过 ``WEBVTT`` 头部以及
    ``NOTE`` / ``STYLE`` / ``REGION`` 块.
    """
    return _parse_subtitle(text)
