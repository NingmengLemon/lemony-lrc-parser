"""LRC 序列化器.

把 :class:`.models.Lyrics` 对象序列化为 LRC 文本。公共入口是
:func:`dump_lrc`
"""

from __future__ import annotations

from collections.abc import Iterator
from io import StringIO
from logging import getLogger

from .models import BasicLyricLine, Lyrics
from .timetag import format_timetag

logger = getLogger(__name__)

__all__ = [
    "dump_lrc",
]


# --------------------------------------------------------------------------- #
# 公共入口
# --------------------------------------------------------------------------- #
def dump_lrc(
    lyrics: Lyrics,
    *,
    with_metadata: bool = True,
    use_bracket_for_byword_tag: bool = False,
    apply_offset_from_metadata: bool = False,
) -> str:
    """把一份 :class:`Lyrics` 序列化为 LRC 文本.

    Args:
        lyrics: 待序列化的歌词对象。
        with_metadata: 是否写出 metadata 段（不影响 offset 的处理逻辑）。
        use_bracket_for_byword_tag: 若为 ``True``，逐字标签使用 ``[...]``；
            否则使用 ``<...>``。
        apply_offset_from_metadata: 是否读取并应用 ``metadata.offset``。
            见下方“offset 语义”。

    offset 语义（与 LRC 规范一致）：
        正 offset 会让歌词显示提前，即 ``display_time = tag_time - offset``。
        当 ``offset > 0`` 时，最早的时间戳可能变为负数；此时函数只应用
        ``min(all_times)`` 这部分“安全” offset，把剩余量写回
        ``metadata.offset`` 交给播放器处理，确保输出的所有时间标签 ``>= 0``。
    """
    buffer = StringIO()

    # 拷贝 metadata 以免污染调用方传入的对象
    metadata = dict(lyrics.metadata)
    offset = _resolve_offset(
        lyrics, metadata, apply_offset_from_metadata=apply_offset_from_metadata
    )

    if with_metadata:
        for key, value in metadata.items():
            buffer.write(f"[{key}: {value}]\n")

    for idx, line in enumerate(lyrics.lines):
        if idx > 0:
            buffer.write("\n")

        line_start = line.start
        if line_start is None:
            logger.warning(f"Skipping line with unknown start time: {line}")
            continue

        # 写主行
        buffer.write(format_timetag(line_start - offset))
        buffer.write(
            _format_words(
                line.content,
                line_start=line_start,
                offset=offset,
                use_bracket_for_byword_tag=use_bracket_for_byword_tag,
            )
        )
        if line.end is not None:
            buffer.write(format_timetag(line.end - offset))
        buffer.write("\n")

        # 写参考行（共享主行的 start）
        for refline in line.reference_lines:
            buffer.write(format_timetag(line_start - offset))
            buffer.write(
                _format_words(
                    refline,
                    line_start=line_start,
                    offset=offset,
                    use_bracket_for_byword_tag=use_bracket_for_byword_tag,
                )
            )
            buffer.write("\n")

    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# 行格式化
# --------------------------------------------------------------------------- #
def _format_words(
    words: BasicLyricLine,
    *,
    line_start: int | None,
    offset: int,
    use_bracket_for_byword_tag: bool,
) -> str:
    """把一行 :data:`BasicLyricLine` 格式化为字符串（不含行首/行末标签）.

    逐字标签在以下情形会被省略：

    * ``idx == 0`` 且 ``word.start == line_start`` —— 行首时间已由调用方
      输出过，不重复。
    * ``idx > 0`` 且 ``words[idx - 1].end == word.start`` —— 与前一词的
      结束时间相接，可省略前缀。
    """
    use_angle = not use_bracket_for_byword_tag
    parts: list[str] = []

    for idx, word in enumerate(words):
        prefix = ""
        suffix = ""

        if word.start is not None:
            if idx == 0:
                if word.start != line_start:
                    prefix = format_timetag(
                        word.start - offset, use_angle_bracket=use_angle
                    )
            elif words[idx - 1].end != word.start:
                prefix = format_timetag(
                    word.start - offset, use_angle_bracket=use_angle
                )

        if word.end is not None:
            suffix = format_timetag(word.end - offset, use_angle_bracket=use_angle)

        parts.append(f"{prefix}{word.content}{suffix}")

    return "".join(parts)


# --------------------------------------------------------------------------- #
# offset 处理
# --------------------------------------------------------------------------- #
def _resolve_offset(
    lyrics: Lyrics,
    metadata: dict[str, str],
    *,
    apply_offset_from_metadata: bool,
) -> int:
    """决定实际应用的 offset 值，必要时把剩余部分写回 ``metadata``.

    Args:
        lyrics: 原始歌词对象（只读，用于收集时间戳）。
        metadata: 调用方已经拷贝出的 metadata 字典。
            ``offset`` 键可能被 pop 出来（``apply_offset_from_metadata=True``
            时）或更新为剩余 offset。
        apply_offset_from_metadata: 是否启用 offset 处理。

    Returns:
        实际应从每个时间戳中扣除的毫秒数，保证不会让任何时间戳变为负。
    """
    if not apply_offset_from_metadata:
        return 0

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

    logger.info(f"Applying global time offset: {offset}ms (from metadata.offset)")

    # 负 offset 只会让时间戳整体变大，无需做越界保护
    if offset <= 0:
        return offset

    all_times = list(_iter_all_timestamps(lyrics))
    if not all_times:
        return offset

    min_time = min(all_times)
    if min_time - offset >= 0:
        return offset

    # 正 offset 超过最小时间戳 → 只应用“安全”部分，剩余写回 metadata
    remaining = offset - min_time
    logger.warning(
        f"Applying offset={offset}ms would make minimum timestamp {min_time}ms "
        f"negative; only applying {min_time}ms, remaining {remaining}ms kept in "
        f"metadata.offset"
    )
    metadata["offset"] = str(remaining)
    return min_time


def _iter_all_timestamps(lyrics: Lyrics) -> Iterator[int]:
    """迭代 :class:`Lyrics` 中出现过的所有时间戳（含参考行）."""
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
