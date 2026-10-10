"""LRC 序列化器.

把 :class:`.models.Lyrics` 对象序列化为 LRC 文本. 公共入口是 :func:`dump_lrc` 与
:func:`dump_with_report`; 后者额外给出 :class:`~.report.DumpReport`, 说明哪些内容
无法无损写出.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from io import StringIO
from logging import getLogger

from ._utils import is_bracket_balanced
from .models import BasicLyricLine, Lyrics, SerializationOptions
from .regex import METATAG_KEY_REGEX, compile_regex
from .report import DumpEvent, DumpReport
from .timetag import format_timetag

logger = getLogger(__name__)

__all__ = [
    "dump_lrc",
    "dump_with_report",
]

#: 事件出口: 收 ``(code, message, level)``, 位置字段由 :class:`_Writer` 补.
_Emit = Callable[[str, str, int], None]


def dump_lrc(lyrics: Lyrics, *, options: SerializationOptions | None = None) -> str:
    """把一份 :class:`Lyrics` 序列化为 LRC 文本.

    Args:
        lyrics: 待序列化的歌词对象.
        options: 序列化选项.
    """
    return _Writer(options).write(lyrics)


def dump_with_report(
    lyrics: Lyrics, *, options: SerializationOptions | None = None
) -> tuple[str, DumpReport]:
    """序列化, 同时返回结构化的序列化报告.

    文本与 :func:`dump_lrc` 完全一致. 报告列出写出时发生的有损或会改变结构的
    处理 (见 :data:`~.report.DumpEventCode`), 位置是 ``lyrics`` 里的行下标. 能无损
    写出的歌词报告为空.

    Returns:
        ``(text, report)``.
    """
    writer = _Writer(options)
    text = writer.write(lyrics)
    return text, DumpReport(events=tuple(writer.events))


class _Writer:
    """一次序列化的上下文: 输出缓冲、选项, 以及收集到的事件."""

    def __init__(self, options: SerializationOptions | None) -> None:
        self.options = options or SerializationOptions()
        self.buffer = StringIO()
        self.events: list[DumpEvent] = []
        self._line_index: int | None = None
        self._reference_index: int | None = None

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def _emit(
        self,
        code: str,
        message: str,
        level: int,
        *,
        metadata_key: str | None = None,
    ) -> None:
        """打日志并记进报告; 位置取当前正在写的行 / 参考行."""
        logger.log(level, message)
        self.events.append(
            DumpEvent(
                code=code,
                message=message,
                line_index=self._line_index,
                reference_index=self._reference_index,
                metadata_key=metadata_key,
            )
        )

    # ------------------------------------------------------------------
    # 写出
    # ------------------------------------------------------------------

    def write(self, lyrics: Lyrics) -> str:
        options = self.options
        buffer = self.buffer

        if options.with_metadata:
            # 必须用 to_pairs(): items() 是 dict 视角, 会丢掉同名重复的 tag.
            for key, value in lyrics.metadata.to_pairs():
                self._check_metadata(key, value)
                buffer.write(f"[{key}: {value}]\n")

        for idx, line in enumerate(lyrics):
            self._line_index = idx
            self._reference_index = None
            if idx > 0:
                buffer.write(options.line_separator)

            line_start = line.start

            # 空正文行: LRC/SPL 里"时间戳后没有文本内容"就是纯结束标记, 方括号写法
            # 无法表达一条空歌词行. 本库沿用 Enhanced LRC 的尖括号写法 (这也是空
            # SRT cue 互转时的形状): 解析端把行首的尖括号标签当行标签, 于是 dumps
            # → loads 仍是不动点. 若改用方括号写出 "[start][end]", 重新解析会把它
            # 当成上一行的结束标记, 静默改掉上一行的时间范围.
            # 它的参考行照常以 "[start]译文" 写在后面, 读回时按同时间戳挂回这一行.
            if not line.text:
                self._write_line_tag(line_start, use_angle=True)
                buffer.write(
                    self._format_line(
                        line.content,
                        line_start=line_start,
                        line_end=line.end,
                        use_bracket=False,
                    )
                )
                if line.end is not None:
                    self._write_line_tag(line.end, use_angle=True)
            else:
                self._write_line_tag(line_start)
                buffer.write(
                    self._format_line(
                        line.content,
                        line_start=line_start,
                        line_end=line.end,
                        use_bracket=options.use_bracket_for_byword_tag,
                    )
                )
                if line.end is not None:
                    self._write_line_tag(line.end)
            buffer.write("\n")

            # 写参考行 (共享主行的 start)
            for ref_idx, refline in enumerate(line.reference_lines):
                self._reference_index = ref_idx
                self._write_reference_line(refline, line_start=line_start)
            self._reference_index = None

        self._line_index = None
        return buffer.getvalue()

    def _write_line_tag(self, ms: int, *, use_angle: bool = False) -> None:
        """写一个行首/行尾时间标签."""
        self.buffer.write(
            format_timetag(
                ms,
                tail_digits=self.options.line_tag_decimal_length,
                use_angle_bracket=use_angle,
            )
        )

    def _write_reference_line(
        self, refline: BasicLyricLine, *, line_start: int
    ) -> None:
        """写一条参考行 (与主行共享 ``line_start``) .

        没有正文的参考行不写出: 只带逐字标签的孤立行在重新解析时是 SPL 的"纯结束
        标记"(方括号行标签 + 无正文), 会去改上一行的时间范围; 既无正文又无逐字
        标签的行则完全没有可保留的信息. 两种情况都跳过, 输出才是稳定的.
        """
        if not refline.text:
            self._emit(
                "textless-reference-skipped",
                f"Skipping text-less reference line of the line at {line_start}ms "
                f"(LRC cannot express it; it would re-parse as an end marker)",
                logging.DEBUG,
            )
            return
        formatted = self._format_line(
            refline,
            line_start=line_start,
            line_end=None,
            use_bracket=self.options.use_bracket_for_byword_tag,
        )
        self._write_line_tag(line_start)
        self.buffer.write(formatted)
        self.buffer.write("\n")

    def _check_metadata(self, key: str, value: str) -> None:
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
            self._emit(
                "metadata-key-unparsable",
                f"Metadata key {key!r} does not match the parser-supported "
                f"pattern {METATAG_KEY_REGEX!r}; it will be lost on re-parsing",
                logging.WARNING,
                metadata_key=key,
            )
        if not is_bracket_balanced(value):
            self._emit(
                "metadata-value-unbalanced",
                f"Metadata value of {key!r} has unbalanced brackets "
                f"(value={value!r}); the value boundary cannot be determined on "
                f"re-parsing, so the whole line will be treated as lyrics instead "
                f"of metadata",
                logging.WARNING,
                metadata_key=key,
            )
        if "\n" in value or "\r" in value:
            self._emit(
                "metadata-value-newline",
                f"Metadata value of {key!r} contains a newline (value={value!r}); "
                "it will break the metadata line structure",
                logging.WARNING,
                metadata_key=key,
            )

    def _format_line(
        self,
        line: BasicLyricLine,
        *,
        line_start: int | None,
        line_end: int | None,
        use_bracket: bool,
    ) -> str:
        """把一行 :data:`BasicLyricLine` 格式化为字符串 (不含行首/行末标签) .

        逐字标签在以下情形会被省略:

        * ``idx == 0`` 且 ``word.start == line_start`` —— 行首时间已由调用方
          输出过, 不重复.
        * ``idx > 0`` 且 ``words[idx - 1].end == word.start`` —— 与前一词的
          结束时间相接, 可省略前缀.
        * 最后一个词元的 ``end`` 与 ``line_end`` 相同 —— 行尾时间已由调用方
          输出, 不重复.
        * 落在 ``[line_start, line_end]`` 之外 —— SPL 规定越界的逐字标记会被
          忽略 (见 :func:`~.parser.parse_line`), 写出来只会得到一个"读不回来"的
          标记; 省略它, ``dumps`` → ``loads`` 才是严格不动点. 这是有损的, 所以
          记 ``byword-out-of-range-omitted``.

        Note:
            当 ``use_bracket`` 且首个词元的 ``start`` 与 ``line_start`` 不同时,
            这个逐字标签紧跟在行首标签之后, 写成 ``[start][word]正文``, 与"重复行
            简写"同形. 解析端按"整行标签是否非递减、正文里有没有别的时间标签"来
            区分两种读法 (见 :mod:`.parser` 的 2b 分支), 所以后果只有两种:

            * 正文里还有别的标签 (后续词元或行尾) 且整行非递减: 读回一行, 行首
              多出一个零文本词元 (``''@start..word``), 正文与时间都不丢. 只记 debug.
            * 否则: 读成两行, 正文重复. 记 warning.

            判据见 :func:`_bracket_first_tag_splits`. 这是选项自身的代价, 只提示
            不改变输出 (行首时间不能省略, 否则信息丢失).
        """
        tail_digits = self.options.word_tag_decimal_length
        use_angle = not use_bracket
        parts: list[str] = []
        last_idx = len(line) - 1
        #: 方括号模式下写成 ``[start][word]`` 的首词元标签 (毫秒), 没有则为 ``None``.
        bracket_first_tag: int | None = None
        #: 首词元标签之后、本函数写出的其它时间标签, 按写出顺序.
        later_tags: list[int] = []
        #: 因越界而省略的时间标签.
        omitted: list[int] = []

        def in_range(value: int) -> bool:
            if line_start is not None and value < line_start:
                return False
            return not (line_end is not None and value > line_end)

        def tag(value: int) -> str:
            return format_timetag(
                value, use_angle_bracket=use_angle, tail_digits=tail_digits
            )

        for idx, word in enumerate(line):
            prefix = ""
            suffix = ""

            if word.start is not None:
                if not in_range(word.start):
                    omitted.append(word.start)
                elif idx == 0:
                    if word.start != line_start:
                        if not use_angle:
                            bracket_first_tag = word.start
                        prefix = tag(word.start)
                elif line[idx - 1].end != word.start:
                    later_tags.append(word.start)
                    prefix = tag(word.start)

            if word.end is not None:
                # 与前一个词元的 end 相接的 start 不写, 但它越界时上面已经记过;
                # 同一个越界时间被相邻词元共享时只记一次.
                if not in_range(word.end):
                    if not (idx < last_idx and line[idx + 1].start == word.end):
                        omitted.append(word.end)
                # 若与调用方输出的行尾标签重复则省略
                elif not (idx == last_idx and word.end == line_end):
                    later_tags.append(word.end)
                    suffix = tag(word.end)

            parts.append(f"{prefix}{word.content}{suffix}")

        if omitted:
            span = f"[{line_start}ms, {'?' if line_end is None else f'{line_end}ms'}]"
            self._emit(
                "byword-out-of-range-omitted",
                f"Line at {line_start}ms: byword tag(s) "
                f"{', '.join(f'{v}ms' for v in omitted)} fall outside the line span "
                f"{span} and are not written (the parser would ignore them, SPL)",
                logging.WARNING,
            )

        if bracket_first_tag is not None and line_start is not None:
            # 调用方会在正文之后写出行尾标签 (参考行传进来的 line_end 是 None).
            if line_end is not None:
                later_tags.append(line_end)
            self._report_bracket_first_tag(line_start, bracket_first_tag, later_tags)

        return "".join(parts)

    def _report_bracket_first_tag(
        self, line_start: int, first_tag: int, later_tags: list[int]
    ) -> None:
        """按真实后果记录方括号首词元标签: 会拆行记 warning, 否则只记 debug."""
        if _bracket_first_tag_splits(line_start, first_tag, later_tags):
            self._emit(
                "bracket-first-tag-splits-line",
                f"Line at {line_start}ms: the first token's byword tag at "
                f"{first_tag}ms is written in square brackets "
                f"(use_bracket_for_byword_tag=True) and nothing after it "
                f"disambiguates; re-parsing will read it as a second line tag and "
                f"duplicate this line's text",
                logging.WARNING,
            )
        else:
            self._emit(
                "bracket-first-tag-adds-token",
                f"Line at {line_start}ms: the first token's byword tag at "
                f"{first_tag}ms is written in square brackets; re-parsing keeps one "
                f"line and adds an empty leading token for the gap (text and timing "
                f"are preserved)",
                logging.DEBUG,
            )


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
