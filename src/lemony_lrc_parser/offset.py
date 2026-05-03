"""Offset 处理工具.

提供全局 offset 的解析与应用逻辑, 供 :mod:`.parser` 与 :mod:`.serializer` 共用.
"""

from __future__ import annotations

from collections.abc import Iterator
from logging import getLogger

from .models import BasicLyricLine, BehaviorConfig, Lyrics

logger = getLogger(__name__)

__all__ = [
    "resolve_offset_delta",
    "apply_offset_to_lyrics",
]


def resolve_offset_delta(
    lyrics: Lyrics,
    metadata: dict[str, str],
    *,
    offset_semantics: str = BehaviorConfig.positive_delays,
) -> int:
    """从 ``metadata`` 中读取 ``offset``, 计算出应**加**到每个时间戳上的有符号增量.

    此函数**只操作 metadata 字典**, 不修改 ``lyrics`` 中的时间戳.
    若裁剪发生, 剩余 offset 会写回 ``metadata["offset"]``.

    Args:
        lyrics: 只读地收集所有时间戳, 用于越界检测.
        metadata: 从中 pop 出 ``offset`` 键; 可能被写回剩余值.
        offset_semantics: ``"positive_delays"`` (默认) 或 ``"positive_advances"``.

    Returns:
        应加到每个时间戳上的毫秒增量 (正数 → 延后, 负数 → 提前) .
    """
    offset_str = metadata.pop("offset", None)
    if not offset_str:
        return 0

    try:
        offset = int(offset_str)
    except ValueError:
        logger.warning(
            f"Cannot parse metadata.offset as integer, ignoring: {offset_str!r}"
        )
        return 0

    # 根据语义确定符号方向
    if offset_semantics == BehaviorConfig.positive_delays:
        delta = offset  # tag_time + offset → 正 offset 延后
    else:
        delta = -offset  # tag_time - offset → 正 offset 提前

    # 裁剪: 确保没有任何时间戳 < 0
    all_times = list(_iter_all_timestamps(lyrics))
    if all_times:
        min_time = min(all_times)
        if min_time + delta < 0:
            safe_delta = -min_time  # 使最小时间戳恰好变为 0
            if offset_semantics == BehaviorConfig.positive_delays:
                remaining = offset - safe_delta
            else:
                remaining = offset + safe_delta  # safe_delta 此时为负
            logger.warning(
                f"Applying offset={offset}ms would make minimum "
                f"timestamp {min_time}ms negative; "
                f"only applying {offset - remaining}ms, "
                f"remaining {remaining}ms kept in metadata.offset"
            )
            metadata["offset"] = str(remaining)
            return safe_delta

    return delta


def apply_offset_to_lyrics(
    lyrics: Lyrics,
    *,
    offset_semantics: str = BehaviorConfig.positive_delays,
) -> int:
    """从 ``lyrics.metadata`` 中读取 offset 并直接应用到所有时间戳 (原地修改).

    Args:
        lyrics: 歌词对象 (会被原地修改).
        offset_semantics: 语义方向, 见 :func:`resolve_offset_delta`.

    Returns:
        实际应用到每个时间戳上的毫秒增量.
    """
    metadata = lyrics.metadata
    delta = resolve_offset_delta(lyrics, metadata, offset_semantics=offset_semantics)
    if delta != 0:
        _apply_delta(lyrics, delta)
        logger.info(
            f"Applied delta={delta}ms to all timestamps "
            f"(semantics={offset_semantics!r})"
        )
    return delta


def _apply_delta(lyrics: Lyrics, delta: int) -> None:
    """将所有时间戳增加 ``delta`` (原地修改)."""
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


def _iter_all_timestamps(lyrics: Lyrics) -> Iterator[int]:
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
