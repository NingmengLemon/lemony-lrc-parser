"""文本与时间范围查询.

:class:`~.models.Lyrics` 的同名方法委托到这里, 公开文档保留在方法上.
"""

from __future__ import annotations

import re
from bisect import bisect_right

from .exceptions import ProgrammingError
from .models import LyricLine, Lyrics

__all__ = [
    "contains_regex",
    "contains_text",
    "find_regex",
    "find_text",
    "lines_in_range",
]


def contains_text(lyrics: Lyrics, needle: str) -> bool:
    """任一行 (含参考行) 是否包含 ``needle``."""
    return any(
        line.contains_text(needle, include_reference_lines=True) for line in lyrics
    )


def find_text(lyrics: Lyrics, needle: str) -> list[LyricLine]:
    """主行或参考行文本包含 ``needle`` 的行, 按现有顺序."""
    return [
        line
        for line in lyrics
        if line.contains_text(needle, include_reference_lines=True)
    ]


def find_regex(
    lyrics: Lyrics,
    pattern: str | re.Pattern[str],
    *,
    include_reference_lines: bool = True,
) -> list[LyricLine]:
    """主行或参考行匹配 ``pattern`` 的行, 按现有顺序."""
    compiled = re.compile(pattern)
    return [
        line
        for line in lyrics
        if compiled.search(line.text)
        or (
            include_reference_lines
            and any(compiled.search(ref.text) for ref in line.reference_lines)
        )
    ]


def contains_regex(
    lyrics: Lyrics,
    pattern: str | re.Pattern[str],
    *,
    include_reference_lines: bool = True,
) -> bool:
    """是否有任意一行匹配 ``pattern``; 参数语义见 :func:`find_regex`."""
    return bool(
        find_regex(lyrics, pattern, include_reference_lines=include_reference_lines)
    )


def lines_in_range(lyrics: Lyrics, start_ms: int, end_ms: int) -> list[LyricLine]:
    """返回与闭区间 ``[start_ms, end_ms]`` 有交集的主行.

    ``end`` 未知的行按下一个 ``start`` 更大的行推断; 最后一行没有 ``end`` 时视为
    延伸到区间终点. 返回顺序沿 ``lyrics`` 现有行序, 参考行不单独返回.

    Raises:
        ProgrammingError: ``end_ms < start_ms``.
    """
    if end_ms < start_ms:
        raise ProgrammingError(
            "end_ms must be greater than or equal to start_ms, "
            f"got {start_ms}..{end_ms}"
        )

    lines = list(lyrics)
    if not lines:
        return []

    starts = sorted(line.start for line in lines)
    result: list[LyricLine] = []
    for line in lines:
        if line.start > end_ms:
            continue
        if line.end is not None:
            effective_end = line.end
        else:
            index = bisect_right(starts, line.start)
            effective_end = starts[index] if index < len(starts) else None
        if effective_end is None or effective_end >= start_ms:
            result.append(line)
    return result
