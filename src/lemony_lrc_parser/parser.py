"""LRC 解析器.

将 LRC 文本转换为 :class:`.models.Lyrics`. 公共入口有:

* :func:`parse_line` —— 解析单行歌词 (不含行首的重复时间标签) .
* :func:`parse_lrc`  —— 解析整份 LRC 文本.

其它以下划线开头的函数均为内部实现细节, 后续版本可能调整.
"""

from __future__ import annotations

import re
from copy import deepcopy
from logging import getLogger

from .exceptions import LyricsParserError
from .models import BasicLyricLine, LyricLine, Lyrics, LyricWord
from .regex import (
    GENERIC_TIMETAG_REGEX,
    LINE_TIMETAG_REGEX,
    METATAG_REGEX,
    compile_regex,
)
from .timetag import _match_to_ms

logger = getLogger(__name__)

__all__ = [
    "parse_line",
    "parse_lrc",
]


def parse_line(line: str) -> BasicLyricLine | None:
    """解析单行歌词为 :data:`.models.BasicLyricLine`.

    输入行应已经去除了行首的重复行时间标签 (见 :func:`_split_leading_line_timetags`) .
    若该行为空或只含空白, 返回 ``None``.

    内部算法:
        1. 用通用时间标签正则把原行拆成 ``text/match`` 交替序列.
        2. 把序列拆成 ``texts`` (长度 N) 与 ``times`` (长度 N-1) 两条平行数组.
        3. 丢弃非单调递增的时间标签 (视为误写并合并相邻文本) .
        4. 用滑动窗口方式把 ``texts[i]`` 和 ``times[i-1] / times[i]`` 绑成
           单个 :class:`LyricWord`.
        5. 去掉首尾的空词, 使 ``result[0].start`` 成为行首、
           ``result[-1].end`` 成为行尾.
    """
    if not line.strip():
        return None

    sequence = _split_on_timetags(line)
    if not sequence or (len(sequence) == 1 and not sequence[0]):
        return None

    if len(sequence) % 2 != 1:
        raise LyricsParserError(
            f"Unexpected sequence length (expected odd): {len(sequence)}"
        )

    texts, times = _unzip_sequence(sequence)

    # 只有一段纯文本、没有任何时间标签
    if len(texts) == 1:
        if times:
            raise LyricsParserError(
                "Inconsistent state: single text segment should not have time tags"
            )
        return [LyricWord(content=texts[0])]

    diff = len(texts) - len(times)
    if diff != 1:
        raise LyricsParserError(
            f"text/time length mismatch: expected diff=1, got {diff}"
        )

    texts, times = _drop_nonmonotonic_times(texts, times)

    result: BasicLyricLine = []
    last_idx = len(texts) - 1
    for idx, content in enumerate(texts):
        word = LyricWord(content=content)
        if idx > 0:
            word.start = times[idx - 1]
        if idx < last_idx:
            word.end = times[idx]
        result.append(word)

    if len(result) < 2:
        raise LyricsParserError(
            f"Expected at least 2 preprocessed elements, got {len(result)}"
        )

    # 去除空头/空尾, 使 [0].start 与 [-1].end 分别对应行首/行尾
    if not result[0].content:
        result.pop(0)
    if not result[-1].content and len(result) > 1:
        result.pop(-1)

    return result


def _split_on_timetags(text: str) -> list[str | re.Match[str]]:
    """按通用时间标签把一行文本拆分为 ``[text, match, text, match, ..., text]``.

    返回结果长度始终为奇数: 以文本开头、以文本结尾, 中间夹杂 match 对象.
    若相邻的两个 match 之间没有文本, 会插入空字符串, 保证 text/match 严格交替.
    """
    pattern = compile_regex(GENERIC_TIMETAG_REGEX)
    result: list[str | re.Match[str]] = []
    last_end = 0
    for match in pattern.finditer(text):
        result.append(text[last_end : match.start()])
        result.append(match)
        last_end = match.end()
    result.append(text[last_end:])
    return result


def _unzip_sequence(
    sequence: list[str | re.Match[str]],
) -> tuple[list[str], list[int]]:
    """把 :func:`_split_on_timetags` 的结果拆成两条独立数组."""
    texts: list[str] = []
    times: list[int] = []
    for item in sequence:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, re.Match):
            times.append(_match_to_ms(item))
        else:
            raise LyricsParserError(
                f"Unexpected element type in sequence: {type(item).__name__}"
            )
    return texts, times


def _drop_nonmonotonic_times(
    texts: list[str], times: list[int]
) -> tuple[list[str], list[int]]:
    """丢弃非严格递增的时间标签, 并把它们前后的文本合并."""
    texts = list(texts)
    times = list(times)
    removed = 0
    for raw_idx in range(len(times)):
        idx = raw_idx - removed
        if idx <= 0:
            continue
        prev_time = times[idx - 1]
        now_time = times[idx]
        if prev_time < now_time:
            continue
        logger.warning(f"Unordered time tag dropped: prev={prev_time}, now={now_time}")
        texts[idx] += texts[idx + 1]
        texts.pop(idx + 1)
        times.pop(idx)
        removed += 1
    return texts, times


def parse_lrc(lrc: str, *, fill_implicit_line_end: bool = False) -> Lyrics:
    """解析一份完整的 LRC 文本.

    Args:
        lrc: LRC 源文本.
        fill_implicit_line_end: 若为 ``True``, 则对没有显式结束时间的行,
            用紧随其后的行开始时间作为隐式结束时间.

    Returns:
        组装完毕的 :class:`Lyrics` 对象.
    """
    metadata: dict[str, str] = {}
    line_pool: dict[int, LyricLine] = {}
    last_tag: int | None = None

    for raw_line in lrc.strip().splitlines():
        line_str = raw_line.strip()

        # 1. metadata 行 (如 [ti: ...]、[offset: 500])
        if meta := _extract_metadata(line_str):
            metadata.update(meta)
            logger.debug(f"Metadata line: {line_str!r}")
            continue

        logger.debug(f"Parsing lyric line: {line_str!r}")

        # 2. 切出行首的重复时间标签
        time_tags, line_str = _split_leading_line_timetags(line_str)
        line = parse_line(line_str)

        # 2a. 行首没有时间标签 → 要么是参考行, 要么是分隔符
        if not time_tags:
            if not line:
                # 空分隔行, 重置参考行锚点
                last_tag = None
                logger.debug("Reference line marker reset")
                continue
            if last_tag is None:
                logger.warning(
                    f"Orphaned lyric line (no anchor): {line!r} (raw={raw_line!r})"
                )
                continue
            logger.debug(f"Adding {line!r} as reference of {line_pool[last_tag]!r}")
            line_pool[last_tag].reference_lines.append(line)
            continue

        # 2b. 行首有时间标签但没有正文 → 占位符 (例如清空当前歌词)
        if not line:
            t = time_tags[0]
            if t not in line_pool:
                line_pool[t] = LyricLine(start=t, content=[LyricWord(content="")])
            continue

        # 2c. 常规行: 可能有多个重复时间标签, 每个都生成一行
        _register_line_at_tags(line_pool, line, time_tags)
        last_tag = time_tags[0] if len(time_tags) == 1 else None

    return _finalize_lyrics(
        metadata, line_pool, fill_implicit_line_end=fill_implicit_line_end
    )


def _register_line_at_tags(
    line_pool: dict[int, LyricLine],
    line: BasicLyricLine,
    time_tags: list[int],
) -> None:
    """把同一行歌词注册到 ``line_pool`` 中所有 ``time_tags`` 对应的时间点上."""
    word_start = line[0].start
    for tag in time_tags:
        if word_start is not None and word_start < tag:
            logger.warning(
                f"Invalid duplicate line tag {tag}ms "
                f"(later than first word start {word_start}ms)"
            )
            continue
        if tag in line_pool:
            # 同一个时间点已有行 → 当前行变为参考行
            line_pool[tag].reference_lines.append(line)
        else:
            # 深拷贝 word 列表, 避免多个 LyricLine 共享同一 LyricWord 实例
            line_pool[tag] = LyricLine(content=[deepcopy(word) for word in line])


def _finalize_lyrics(
    metadata: dict[str, str],
    line_pool: dict[int, LyricLine],
    *,
    fill_implicit_line_end: bool,
) -> Lyrics:
    """把 ``line_pool`` 按时间排序、补全行首/行尾时间并装进 :class:`Lyrics`."""
    lyrics = Lyrics(metadata=metadata)
    sorted_items = sorted(line_pool.items(), key=lambda kv: kv[0])

    for idx, (line_start, line) in enumerate(sorted_items):
        line.start = line_start

        # 把最后一个 word 的 end 提升为整行 end
        last_word = line.content[-1]
        if last_word.end is not None:
            line.end, last_word.end = last_word.end, None

        # 可选: 用下一行的开始时间作为当前行的隐式结束
        if fill_implicit_line_end and line.end is None and idx + 1 < len(sorted_items):
            line.end = sorted_items[idx + 1][0]

        lyrics.lines.append(line)

    return lyrics


def _split_leading_line_timetags(raw_line: str) -> tuple[list[int], str]:
    """从一行开头连续剥离 ``[mm:ss.xxx]`` 行时间标签.

    Returns:
        ``(times, remainder)``, ``times`` 为毫秒列表, ``remainder`` 为剥离后
        的剩余文本.
    """
    pattern = compile_regex(f"^{LINE_TIMETAG_REGEX}")
    times: list[int] = []
    while (match := pattern.match(raw_line)) is not None:
        times.append(_match_to_ms(match))
        raw_line = raw_line[match.end() :]
    return times, raw_line


def _extract_metadata(line: str) -> dict[str, str]:
    """从一行字符串中提取 metadata 标签 ``[key: value]``."""
    pattern = compile_regex(METATAG_REGEX)
    return {match["key"]: match["value"] for match in pattern.finditer(line)}
