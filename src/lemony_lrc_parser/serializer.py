"""LRC 序列化器.

把 :class:`.models.Lyrics` 对象序列化为 LRC 文本. 公共入口是
:func:`dump_lrc`
"""

from __future__ import annotations

from io import StringIO
from logging import getLogger

from .models import BasicLyricLine, Lyrics, SerializationOptions
from .offset import resolve_offset_delta
from .timetag import format_timetag

logger = getLogger(__name__)

__all__ = [
    "dump_lrc",
]


def dump_lrc(lyrics: Lyrics, *, options: SerializationOptions | None = None) -> str:
    """把一份 :class:`Lyrics` 序列化为 LRC 文本.

    Args:
        lyrics: 待序列化的歌词对象.
        options: 序列化选项.

    在序列化时应用 offset 意味着时间标签会被整体偏移.
    若 ``apply_offset_from_metadata=True``, 则从 ``metadata.offset`` 读入偏移量
    并应用到输出的每个时间标签, **Lyrics 对象本身的时间戳不受影响**.

    Offset 语义 (foobar2000 兼容) :
        当 ``offset_semantics="positive_delays"`` (默认) 时:
            ``display_time = tag_time + offset``
            正 offset → 歌词延后显示.
        当 ``offset_semantics="positive_advances"`` 时:
            ``display_time = tag_time - offset``
            正 offset → 歌词提前显示 (旧行为).
    """
    buffer = StringIO()

    options = options or SerializationOptions()
    # 拷贝 metadata 以免污染调用方传入的对象
    metadata = dict(lyrics.metadata)

    if options.apply_offset_from_metadata and not lyrics._offset_applied:
        delta = resolve_offset_delta(
            lyrics, metadata, offset_semantics=options.offset_semantics
        )
    else:
        delta = 0

    if options.with_metadata:
        for key, value in metadata.items():
            if options.skip_empty_metadata and not value.strip():
                continue
            buffer.write(f"[{key}: {value}]\n")

    for idx, line in enumerate(lyrics.lines):
        if idx > 0:
            buffer.write("\n")

        line_start = line.start
        if line_start is None:
            logger.warning(f"Skipping line with unknown start time: {line}")
            continue

        # 写主行
        buffer.write(format_timetag(line_start + delta))
        buffer.write(
            _format_words(
                line.content,
                line_start=line_start,
                delta=delta,
                use_bracket_for_byword_tag=options.use_bracket_for_byword_tag,
                tail_digits=options.word_tag_decimal_length,
            )
        )
        if line.end is not None:
            buffer.write(
                format_timetag(
                    line.end + delta, tail_digits=options.line_tag_decimal_length
                )
            )
        buffer.write("\n")

        # 写参考行 (共享主行的 start)
        for refline in line.reference_lines:
            buffer.write(
                format_timetag(
                    line_start + delta, tail_digits=options.line_tag_decimal_length
                )
            )
            buffer.write(
                _format_words(
                    refline,
                    line_start=line_start,
                    delta=delta,
                    use_bracket_for_byword_tag=options.use_bracket_for_byword_tag,
                    tail_digits=options.word_tag_decimal_length,
                )
            )
            buffer.write("\n")

    return buffer.getvalue()


def _format_words(
    words: BasicLyricLine,
    *,
    line_start: int | None,
    delta: int,
    use_bracket_for_byword_tag: bool,
    tail_digits: int,
) -> str:
    """把一行 :data:`BasicLyricLine` 格式化为字符串 (不含行首/行末标签) .

    逐字标签在以下情形会被省略:

    * ``idx == 0`` 且 ``word.start == line_start`` —— 行首时间已由调用方
      输出过, 不重复.
    * ``idx > 0`` 且 ``words[idx - 1].end == word.start`` —— 与前一词的
      结束时间相接, 可省略前缀.
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
                        word.start + delta,
                        use_angle_bracket=use_angle,
                        tail_digits=tail_digits,
                    )
            elif words[idx - 1].end != word.start:
                prefix = format_timetag(
                    word.start + delta,
                    use_angle_bracket=use_angle,
                    tail_digits=tail_digits,
                )

        if word.end is not None:
            suffix = format_timetag(
                word.end + delta,
                use_angle_bracket=use_angle,
                tail_digits=tail_digits,
            )

        parts.append(f"{prefix}{word.content}{suffix}")

    return "".join(parts)
