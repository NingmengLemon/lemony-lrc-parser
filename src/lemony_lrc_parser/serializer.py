"""LRC 序列化器.

把 :class:`.models.Lyrics` 对象序列化为 LRC 文本. 公共入口是
:func:`dump_lrc`
"""

from __future__ import annotations

from io import StringIO
from logging import getLogger

from ._utils import is_bracket_balanced
from .models import BasicLyricLine, Lyrics, SerializationOptions
from .regex import METATAG_KEY_REGEX, compile_regex
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
    """
    buffer = StringIO()

    options = options or SerializationOptions()

    if options.with_metadata:
        for key, value in lyrics.metadata.items():
            _warn_non_roundtrippable_metadata(key, value)
            buffer.write(f"[{key}: {value}]\n")

    sep = options.line_separator

    def write_line_tag(ms: int) -> None:
        """写一个行首/行尾方括号时间标签."""
        buffer.write(
            format_timetag(
                ms,
                tail_digits=options.line_tag_decimal_length,
                use_angle_bracket=False,
            )
        )

    for idx, line in enumerate(lyrics):
        if idx > 0:
            buffer.write(sep)

        line_start = line.start

        # 空正文 + 显式行尾 → 输出形如 "[00:01.000][00:02.000]". 重新解析时
        # 连续的行首标签会被读成"折叠标签", 变成两个空占位行, 行数翻倍.
        if line.end is not None and not line.text:
            logger.warning(
                f"Line at {line_start}ms has an explicit end ({line.end}ms) but no "
                "text; it is written as '[start][end]', which re-parses as two "
                "empty placeholder lines instead of one line with a range"
            )

        # 写主行
        write_line_tag(line_start)
        buffer.write(
            _format_line(
                line.content,
                line_start=line_start,
                line_end=line.end,
                use_bracket_for_byword_tag=options.use_bracket_for_byword_tag,
                tail_digits=options.word_tag_decimal_length,
            )
        )
        if line.end is not None:
            write_line_tag(line.end)
        buffer.write("\n")

        # 写参考行 (共享主行的 start)
        for refline in line.reference_lines:
            formatted = _format_line(
                refline,
                line_start=line_start,
                line_end=None,
                use_bracket_for_byword_tag=options.use_bracket_for_byword_tag,
                tail_digits=options.word_tag_decimal_length,
            )
            if not formatted:
                # 既无正文、也没有任何需要写出的逐字标签 → 这个参考行里没有
                # 任何可保留的信息, 写出的孤立行标签在重新解析时只会被当成
                # "该时间点已存在" 的占位而被忽略. 跳过它, 输出才是稳定的
                # (否则同一份歌词 dump 两次会多出一行).
                logger.debug(
                    f"Skipping empty reference line of the line at {line_start}ms "
                    f"(no text and no byword tags to write)"
                )
                continue
            write_line_tag(line_start)
            buffer.write(formatted)
            buffer.write("\n")

    return buffer.getvalue()


def _warn_non_roundtrippable_metadata(key: str, value: str) -> None:
    """对重新解析时无法完整还原的 metadata 项发出 warning.

    三项判据:

    * key 必须符合 ``METATAG_KEY_REGEX``;
    * value 里的方括号必须**配对平衡** (解析端用配对方括号确定 value 边界,
      所以 ``Album [Deluxe]`` 可以往返, 而 ``50% ]off`` 不行);
    * value 不能含换行.

    这里只提示、不阻止写出 —— 数据保留在输出文本里总好过静默丢弃.

    解析端是否放宽 metadata key 字符集 (如允许非 ASCII key) 见 feature
    ideas 中的 F-META-KEY, 属于独立决策, 此告警不预设其结论.
    """
    if compile_regex(rf"^{METATAG_KEY_REGEX}$").match(key) is None:
        logger.warning(
            f"Metadata key {key!r} does not match the parser-supported "
            f"pattern {METATAG_KEY_REGEX!r}; it will be lost on re-parsing"
        )
    if not is_bracket_balanced(value):
        logger.warning(
            f"Metadata value of {key!r} has unbalanced brackets (value={value!r}); "
            "the value boundary cannot be determined on re-parsing, so the whole "
            "line will be treated as lyrics instead of metadata"
        )
    if "\n" in value or "\r" in value:
        logger.warning(
            f"Metadata value of {key!r} contains a newline (value={value!r}); "
            "it will break the metadata line structure"
        )


def _format_line(
    line: BasicLyricLine,
    *,
    line_start: int | None,
    line_end: int | None,
    use_bracket_for_byword_tag: bool,
    tail_digits: int,
) -> str:
    """把一行 :data:`BasicLyricLine` 格式化为字符串 (不含行首/行末标签) .

    逐字标签在以下情形会被省略:

    * ``idx == 0`` 且 ``word.start == line_start`` —— 行首时间已由调用方
      输出过, 不重复.
    * ``idx > 0`` 且 ``words[idx - 1].end == word.start`` —— 与前一词的
      结束时间相接, 可省略前缀.
    * 最后一个词元的 ``end`` 与 ``line_end`` 相同 —— 行尾时间已由调用方
      输出, 不重复.

    Note:
        当 ``use_bracket_for_byword_tag=True`` 且首个词元的 ``start`` 与
        ``line_start`` 不同时, 这个"逐字标签"会紧跟在行首标签之后写成
        ``[start][word]``; 重新解析时它会被读成行首标签 (折叠标签), 整行被
        拆成两行. 该写法属于选项自身的代价, 此处只告警不改变输出 (行首时间
        不能省略, 否则信息丢失).
    """
    use_angle = not use_bracket_for_byword_tag
    parts: list[str] = []
    last_idx = len(line) - 1

    for idx, word in enumerate(line):
        prefix = ""
        suffix = ""

        if word.start is not None:
            if idx == 0:
                if word.start != line_start:
                    if not use_angle:
                        tag = format_timetag(
                            word.start,
                            use_angle_bracket=False,
                            tail_digits=tail_digits,
                        )
                        logger.warning(
                            f"Byword tag for the first token of the line starting "
                            f"at {line_start}ms is written as '{tag}' because "
                            f"use_bracket_for_byword_tag=True; re-parsing will read "
                            f"it as a line time tag and split this line into two"
                        )
                    prefix = format_timetag(
                        word.start,
                        use_angle_bracket=use_angle,
                        tail_digits=tail_digits,
                    )
            elif line[idx - 1].end != word.start:
                prefix = format_timetag(
                    word.start,
                    use_angle_bracket=use_angle,
                    tail_digits=tail_digits,
                )

        if word.end is not None:
            # 若与调用方输出的行尾标签重复则省略
            if idx == last_idx and word.end == line_end:
                pass
            else:
                suffix = format_timetag(
                    word.end,
                    use_angle_bracket=use_angle,
                    tail_digits=tail_digits,
                )

        parts.append(f"{prefix}{word.content}{suffix}")

    return "".join(parts)
