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
        # 必须用 to_pairs(): items() 是 dict 视角, 会丢掉同名重复的 tag.
        for key, value in lyrics.metadata.to_pairs():
            _warn_non_roundtrippable_metadata(key, value)
            buffer.write(f"[{key}: {value}]\n")

    sep = options.line_separator

    def write_line_tag(ms: int, *, use_angle: bool = False) -> None:
        """写一个行首/行尾时间标签."""
        buffer.write(
            format_timetag(
                ms,
                tail_digits=options.line_tag_decimal_length,
                use_angle_bracket=use_angle,
            )
        )

    for idx, line in enumerate(lyrics):
        if idx > 0:
            buffer.write(sep)

        line_start = line.start

        # 空正文行: LRC/SPL 里"时间戳后没有文本内容"就是纯结束标记, 方括号写法
        # 无法表达一条空歌词行. 本库沿用 Enhanced LRC 的尖括号写法 (这也是空 SRT
        # cue 互转时的形状): 解析端把行首的尖括号标签当行标签, 于是 dumps → loads
        # 仍是不动点. 若改用方括号写出 "[start][end]", 重新解析会把它当成上一行的
        # 结束标记, 静默改掉上一行的时间范围.
        if not line.text:
            if line.reference_lines:
                logger.warning(
                    f"Line at {line_start}ms has no text but has "
                    f"{len(line.reference_lines)} reference line(s); they are "
                    f"written as separate lines and will re-parse as translations "
                    f"of this empty line"
                )
            write_line_tag(line_start, use_angle=True)
            buffer.write(
                _format_line(
                    line.content,
                    line_start=line_start,
                    line_end=line.end,
                    use_bracket_for_byword_tag=False,
                    tail_digits=options.word_tag_decimal_length,
                )
            )
            if line.end is not None:
                write_line_tag(line.end, use_angle=True)
            buffer.write("\n")
            for refline in line.reference_lines:
                _write_reference_line(
                    buffer,
                    refline,
                    line_start=line_start,
                    options=options,
                )
            continue

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
            _write_reference_line(
                buffer, refline, line_start=line_start, options=options
            )

    return buffer.getvalue()


def _write_reference_line(
    buffer: StringIO,
    refline: BasicLyricLine,
    *,
    line_start: int,
    options: SerializationOptions,
) -> None:
    """写一条参考行 (与主行共享 ``line_start``) .

    没有正文的参考行不写出: 只带逐字标签的孤立行在重新解析时是 SPL 的"纯结束
    标记"(方括号行标签 + 无正文), 会去改上一行的时间范围; 既无正文又无逐字标签
    的行则完全没有可保留的信息. 两种情况都跳过, 输出才是稳定的.
    """
    formatted = _format_line(
        refline,
        line_start=line_start,
        line_end=None,
        use_bracket_for_byword_tag=options.use_bracket_for_byword_tag,
        tail_digits=options.word_tag_decimal_length,
    )
    if not refline.text:
        logger.debug(
            f"Skipping text-less reference line of the line at {line_start}ms "
            f"(LRC cannot express it; it would re-parse as an end marker)"
        )
        return
    buffer.write(
        format_timetag(
            line_start,
            tail_digits=options.line_tag_decimal_length,
            use_angle_bracket=False,
        )
    )
    buffer.write(formatted)
    buffer.write("\n")


def _warn_non_roundtrippable_metadata(key: str, value: str) -> None:
    """对重新解析时无法完整还原的 metadata 项发出 warning.

    三项判据:

    * key 必须符合 ``METATAG_KEY_REGEX``;
    * value 里的方括号必须**配对平衡** (解析端用配对方括号确定 value 边界,
      所以 ``Album [Deluxe]`` 可以往返, 而 ``50% ]off`` 不行);
    * value 不能含换行.

    这里只提示、不阻止写出 —— 数据保留在输出文本里总好过静默丢弃.

    解析端是否放宽 metadata key 字符集 (如允许非 ASCII key) 见
    ``docs/roadmap.md`` 的 META-3, 属于独立决策, 此告警不预设其结论.
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
    * 落在 ``[line_start, line_end]`` 之外 —— SPL 规定越界的逐字标记会被忽略
      (见 :func:`~.parser.parse_line`), 写出来只会得到一个"读不回来"的标记;
      省略它, ``dumps`` → ``loads`` 才是严格不动点.

    Note:
        当 ``use_bracket_for_byword_tag=True`` 且首个词元的 ``start`` 与
        ``line_start`` 不同时, 这个逐字标签紧跟在行首标签之后, 写成
        ``[start][word]正文``, 与"重复行简写"同形. 解析端按"整行标签是否非递减、
        正文里有没有别的时间标签"来区分两种读法 (见 :mod:`.parser` 的 2b 分支),
        所以后果只有两种:

        * 正文里还有别的标签 (后续词元或行尾) 且整行非递减: 读回一行, 行首多出
          一个零文本词元 (``''@start..word``), 正文与时间都不丢. 只记 debug.
        * 否则: 读成两行, 正文重复. 记 warning.

        判据见 :func:`_bracket_first_tag_splits`. 这是选项自身的代价, 只提示不改变
        输出 (行首时间不能省略, 否则信息丢失).
    """
    use_angle = not use_bracket_for_byword_tag
    parts: list[str] = []
    last_idx = len(line) - 1
    #: 方括号模式下写成 ``[start][word]`` 的首词元标签 (毫秒), 没有则为 ``None``.
    bracket_first_tag: int | None = None
    #: 首词元标签之后、本函数写出的其它时间标签, 按写出顺序.
    later_tags: list[int] = []

    def in_range(value: int) -> bool:
        if line_start is not None and value < line_start:
            return False
        return not (line_end is not None and value > line_end)

    for idx, word in enumerate(line):
        prefix = ""
        suffix = ""

        if word.start is not None and in_range(word.start):
            if idx == 0:
                if word.start != line_start:
                    if not use_angle:
                        bracket_first_tag = word.start
                    prefix = format_timetag(
                        word.start,
                        use_angle_bracket=use_angle,
                        tail_digits=tail_digits,
                    )
            elif line[idx - 1].end != word.start:
                later_tags.append(word.start)
                prefix = format_timetag(
                    word.start,
                    use_angle_bracket=use_angle,
                    tail_digits=tail_digits,
                )

        if word.end is not None and in_range(word.end):
            # 若与调用方输出的行尾标签重复则省略
            if idx == last_idx and word.end == line_end:
                pass
            else:
                later_tags.append(word.end)
                suffix = format_timetag(
                    word.end,
                    use_angle_bracket=use_angle,
                    tail_digits=tail_digits,
                )

        parts.append(f"{prefix}{word.content}{suffix}")

    if bracket_first_tag is not None and line_start is not None:
        # 调用方会在正文之后写出行尾标签 (参考行传进来的 line_end 是 None).
        if line_end is not None:
            later_tags.append(line_end)
        _report_bracket_first_tag(line_start, bracket_first_tag, later_tags)

    return "".join(parts)


def _bracket_first_tag_splits(
    line_start: int, first_tag: int, later_tags: list[int]
) -> bool:
    """``[line_start][first_tag]正文...`` 重新解析时是否会被拆成两行.

    与 :mod:`.parser` 的 2b 分支同一判据: 正文里还有别的时间标签, 且整行标签
    非递减, 才读成"行标签 + 延迟首字"的一行; 否则按重复行简写展开.
    ``tests/test_properties.py`` 用真实的重新解析结果核对这条判据.
    """
    values = [line_start, first_tag, *later_tags]
    non_decreasing = all(a <= b for a, b in zip(values, values[1:]))
    return not (later_tags and non_decreasing)


def _report_bracket_first_tag(
    line_start: int, first_tag: int, later_tags: list[int]
) -> None:
    """按真实后果记录方括号首词元标签: 会拆行记 warning, 否则只记 debug."""
    if _bracket_first_tag_splits(line_start, first_tag, later_tags):
        logger.warning(
            f"Line at {line_start}ms: the first token's byword tag at {first_tag}ms is "
            f"written in square brackets (use_bracket_for_byword_tag=True) and nothing "
            f"after it disambiguates; re-parsing will read it as a second line "
            f"tag and duplicate this line's text"
        )
    else:
        logger.debug(
            f"Line at {line_start}ms: the first token's byword tag at {first_tag}ms is "
            f"written in square brackets; re-parsing keeps one line and adds an empty "
            f"leading token for the gap (text and timing are preserved)"
        )
