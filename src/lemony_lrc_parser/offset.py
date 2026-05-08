from __future__ import annotations

from collections.abc import Iterator

from .models import BasicLyricLine, Lyrics

__all__ = [
    "apply_delta",
    "iter_all_timestamps",
]


def apply_delta(lyrics: Lyrics, delta: int) -> None:
    """将所有时间戳增加 ``delta`` ms

    注意此处为底层函数没有下溢保护, 且为原地修改"""
    for line in lyrics.lines:
        if line.start is not None:
            line.start += delta
        if line.end is not None:
            line.end += delta
        _apply_word_delta(line.content, delta)
        for refline in line.reference_lines:
            _apply_word_delta(refline, delta)


def _apply_word_delta(words: BasicLyricLine, delta: int) -> None:
    for word in words:
        if word.start is not None:
            word.start += delta
        if word.end is not None:
            word.end += delta


def iter_all_timestamps(lyrics: Lyrics) -> Iterator[int]:
    """迭代 :class:`Lyrics` 中出现过的所有时间戳 (含参考行)."""
    for line in lyrics.lines:
        if line.start is not None:
            yield line.start
        if line.end is not None:
            yield line.end
        yield from _iter_word_timestamps(line.content)
        for refline in line.reference_lines:
            yield from _iter_word_timestamps(refline)


def _iter_word_timestamps(words: BasicLyricLine) -> Iterator[int]:
    """从一个 word 序列中迭代出所有非空时间戳."""
    for word in words:
        if word.start is not None:
            yield word.start
        if word.end is not None:
            yield word.end
