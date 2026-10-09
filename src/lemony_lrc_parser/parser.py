"""LRC 解析器.

将 LRC 文本转换为 :class:`.models.Lyrics`. 公共入口有:

* :func:`parse_line` —— 解析单行歌词 (不含行首的重复时间标签) .
* :func:`parse_lrc`  —— 解析整份 LRC 文本.
* :func:`parse_with_report` —— 同上, 但额外返回结构化的 :class:`.report.ParseReport`.

内部实现是 :class:`LrcParser`: 解析状态挂在实例上, :func:`parse_lrc` 只是它的薄
包装. 其它以下划线开头的函数均为内部实现细节, 后续版本可能调整.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from logging import getLogger

from ._utils import match_to_ms
from .exceptions import InvalidLyricsError, LyricsParserError
from .metadata import Metadata
from .models import BasicLyricLine, LyricLine, Lyrics, LyricToken, ParseOptions
from .regex import (
    GENERIC_TIMETAG_REGEX,
    LINE_TIMETAG_REGEX,
    METATAG_KEY_REGEX,
    WORD_TIMETAG_REGEX,
    compile_regex,
)
from .report import STRICT_ERROR_CODES, ParseEvent, ParseReport

logger = getLogger(__name__)

#: 事件回调的签名: ``(code, message) -> None``.
#:
#: :func:`parse_line` 与 :func:`_finalize_lyrics` 用它在内部事件发生时就地通知
#: 调用方; 行号 / 原始行由调用方自己补 (只有它知道).
EventCallback = Callable[[str, str], None]

__all__ = [
    "parse_line",
    "parse_lrc",
    "parse_with_report",
]


def parse_line(
    line: str,
    *,
    line_start: int | None = None,
    line_end: int | None = None,
    on_event: EventCallback | None = None,
) -> BasicLyricLine | None:
    """解析单行歌词为 :data:`.models.LyricLine` 的内容部分.

    输入行应已经去除了行首的重复行时间标签 (见 :func:`_split_leading_line_timetags`) .
    若该行为空或只含空白, 返回 ``None``.

    Args:
        line: 待解析的行文本 (可以含行首的时间标签) .
        line_start: 本行的开始时间 (毫秒) . 早于它的时间标签会被忽略 (SPL:
            逐字标记必须落在行开始与结束时间之间, 否则该标记被忽略) .
            ``None`` 表示未知, 不做下界过滤.
        line_end: 本行的结束时间 (毫秒) . 晚于它的时间标签同样被忽略.
            ``None`` 表示未知, 不做上界过滤.
        on_event: 忽略逐字标记时的回调, 收到 ``(code, message)``; 见
            :data:`.report.ParseEventCode`. 默认 ``None`` 表示只打日志.

    Note:
        "忽略" 指丢弃标记本身并把两侧文本合并, 不丢字. 这与
        :func:`_drop_unusable_times` 对非递增标记的处理是同一套动作.

    内部算法:
        1. 用通用时间标签正则把原行拆成 ``text/match`` 交替序列.
        2. 把序列拆成 ``texts`` (长度 N) 与 ``times`` (长度 N-1) 两条平行数组.
        3. 丢弃越界或非单调递增的时间标签 (视为误写并合并相邻文本) .
        4. 用滑动窗口方式把 ``texts[i]`` 和 ``times[i-1] / times[i]`` 绑成
           单个 :class:`LyricToken`.
        5. 去掉首尾的空词, 使 ``result[0].start`` 成为行首、
           ``result[-1].end`` 成为行尾.
    """
    if not line.strip():
        return None

    sequence = _split_on_timetags(line)
    if not sequence or (len(sequence) == 1 and not sequence[0]):
        return None

    if len(sequence) % 2 != 1:
        raise InvalidLyricsError(
            f"Unexpected sequence length (expected odd): {len(sequence)}"
        )

    texts, times = _unzip_sequence(sequence)

    # 只有一段纯文本、没有任何时间标签
    if len(texts) == 1:
        if times:
            raise LyricsParserError(
                "Inconsistent state: single text segment should not have time tags"
            )
        return BasicLyricLine([LyricToken(content=texts[0])])

    diff = len(texts) - len(times)
    if diff != 1:
        raise InvalidLyricsError(
            f"text/time length mismatch: expected diff=1, got {diff}"
        )

    # 行尾标签 (SPL 的显式行尾) 与末词元时间相同时会被当成"重复标签"合并掉,
    # 于是整行的结束时间就丢了. 行尾时间由调用方另行记在 ``LyricLine.end`` 上
    # (见 :func:`_apply_explicit_line_end`), 这里只保证词元时间不退化。
    texts, times = _drop_unusable_times(
        texts, times, line_start=line_start, line_end=line_end, on_event=on_event
    )

    # 所有时间标签都被忽略 → 退化成一行纯文本 (文本已被合并成一段)
    if not times:
        return BasicLyricLine([LyricToken(content="".join(texts))])

    result = BasicLyricLine()
    last_idx = len(texts) - 1
    for idx, content in enumerate(texts):
        word = LyricToken(content=content)
        if idx > 0:
            word.start = times[idx - 1]
        if idx < last_idx:
            word.end = times[idx]
        result.append(word)

    # 防御性检查: 当前实现下不可达——首个时间标签永远不会被
    # _drop_unusable_times 丢弃, 因此 times 非空时 texts 至少剩 2 段.
    # 保留以防未来改动破坏该不变量.
    if len(result) < 2:  # pragma: no cover
        raise InvalidLyricsError(
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
            times.append(match_to_ms(item))
        else:
            raise LyricsParserError(
                f"Unexpected element type in sequence: {type(item).__name__}"
            )
    return texts, times


def _drop_unusable_times(
    texts: list[str],
    times: list[int],
    *,
    line_start: int | None = None,
    line_end: int | None = None,
    on_event: EventCallback | None = None,
) -> tuple[list[str], list[int]]:
    """丢弃越界或非严格递增的时间标签, 并把它们前后的文本合并.

    三类情况区别对待 (真实语料统计见 docs/research/corpus.md: 某 6536 份
    .lrc 语料里 "相等" 出现 1917 次, "递减" 0 次, 越界 0 次):

    * 早于 ``line_start`` 或晚于 ``line_end``: SPL 明文规定逐字标记必须落在行
      开始与结束时间之间, 否则**忽略该标记** —— 行标签/行尾标签为准, 记
      ``warning`` (数据自相矛盾, 用户应当知道) .
    * ``now == prev``: 逐字行里很常见 (空格词元与下一个词共享时间戳), 合并后
      语义不变, 只记 ``debug``, 不当成用户需要处理的异常.
    * ``now < prev``: 真的乱序, 记 ``warning``.

    Args:
        on_event: 前三种情况各自的回调 (见 :data:`.report.ParseEventCode`);
            相等合并属于正常写法, 不进报告. 默认 ``None`` 表示只打日志.
    """
    texts = list(texts)
    times = list(times)

    def _report(code: str, message: str) -> None:
        """打日志并通知回调 (相等合并那类正常写法不走这里)."""
        logger.warning(message)
        if on_event is not None:
            on_event(code, message)

    idx = 0
    while idx < len(times):
        value = times[idx]
        if line_start is not None and value < line_start:
            _report(
                "byword-before-line-start",
                f"Time tag {value}ms is before the line start {line_start}ms; "
                f"ignoring the tag and keeping the line tag (SPL)",
            )
        elif line_end is not None and value > line_end:
            _report(
                "byword-after-line-end",
                f"Time tag {value}ms is after the line end {line_end}ms; "
                f"ignoring the tag and keeping the line end (SPL)",
            )
        elif idx > 0 and times[idx - 1] > value:
            _report(
                "byword-unordered",
                f"Unordered time tag dropped: prev={times[idx - 1]}ms, now={value}ms",
            )
        elif idx > 0 and times[idx - 1] == value:
            logger.debug(f"Redundant equal time tag merged: {value}ms")
        else:
            idx += 1
            continue
        # 丢弃 times[idx], 把它两侧的文本合并成一段 (不丢字)
        texts[idx] += texts[idx + 1]
        texts.pop(idx + 1)
        times.pop(idx)
    return texts, times


class LrcParser:
    """一次解析的上下文 (内部对象, 后续版本可能调整).

    把原先散在 :func:`parse_lrc` 局部变量里的状态收进实例: 已提取的 metadata、
    行池、参考行锚点、结束标记的收尾目标, 以及本次解析的 :class:`ParseOptions`.
    对外入口仍然是 :func:`parse_lrc`, 它只是薄包装.

    两种用法:

    * 整份解析: ``LrcParser(options).parse(text)``。
    * 逐步喂行: 自己按行调用 :meth:`parse_raw_line`, 最后 :meth:`finalize`;
      这样调用方能在中途查看行池, 也是解析报告 / source map 的挂载点.

    Note:
        状态挂在实例上, 所以同一个实例不要跨文档复用而不重置: :meth:`parse` 会
        先调用 :meth:`reset`, 手动逐行喂时重置由调用方负责.

    Note:
        "丢了什么 / 忽略了什么" 除日志外还会累积成 :attr:`report`. 只有真正值得
        调用方知道的事件才进报告, 所以干净文件的报告是空的; 日志格式不受影响
        (逐字标记那几条仍按原格式打印, 但报告里会补上行号).
    """

    def __init__(self, options: ParseOptions | None = None) -> None:
        """构造解析器.

        Args:
            options: 解析选项; ``None`` 表示使用默认值.
        """
        self.options: ParseOptions = options or ParseOptions()
        self._line_tag_check = compile_regex(f"^{LINE_TIMETAG_REGEX}")
        self._word_tag_check = compile_regex(f"^{WORD_TIMETAG_REGEX}")
        self.reset()

    def reset(self) -> None:
        """清空已累积的解析状态 (行池 / metadata / 锚点 / 报告), 选项保持不变."""
        #: 已提取的 ID 标签; 同名 key 全部保留 (见 :class:`~.metadata.Metadata`).
        self.metadata: Metadata = Metadata()
        #: 时间点 -> 歌词行. 同一时间点后到的行会挂成先到者的参考行.
        self.line_pool: dict[int, LyricLine] = {}
        #: 最近一个可作参考行锚点的时间点; 空分隔行会把它重置.
        self.last_tag: int | None = None
        #: 最近一行**有正文**的歌词所占的时间点. 与 ``last_tag`` 不同, 它不被空行
        #: 重置, 也不被参考行/结束标记影响 —— SPL 的"纯结束标记"要收尾的正是这一行.
        self.last_text_tags: list[int] = []
        self._events: list[ParseEvent] = []
        self._reference_lines_attached = 0
        self._end_markers_applied = 0

    @property
    def report(self) -> ParseReport:
        """本次解析的结构化报告 (每次访问都按当前已累积的事件重建)."""
        return ParseReport(
            events=tuple(self._events),
            reference_lines_attached=self._reference_lines_attached,
            end_markers_applied=self._end_markers_applied,
        )

    def parse(self, lrc: str) -> Lyrics:
        """解析整份 LRC 文本, 返回组装好的 :class:`Lyrics`.

        Args:
            lrc: LRC 源文本.
        """
        self.reset()
        # 去除开头可能存在的 BOM (例如调用方直接 loads() 未按 utf-8-sig 解码的
        # 文本). 若不去除, BOM 会使行首锚定正则失配, 导致首行被当作无锚点
        # 孤儿行而静默丢弃. BOM 本身不含换行, 去除不影响行号计数.
        lrc = lrc.removeprefix("\ufeff")
        # NOTE: 不再使用 lrc.strip().splitlines(), 而是保留前导空行以正确计数行号.
        # 空行不会产生有效歌词, 但会消耗 line_no 并产生 debug 日志.
        for line_no, raw_line in enumerate(lrc.splitlines(), start=1):
            self.parse_raw_line(line_no, raw_line)
        return self.finalize()

    def _record(
        self,
        code: str,
        message: str,
        *,
        line_no: int | None = None,
        raw_line: str | None = None,
    ) -> None:
        """记进报告; 严格模式下命中 :data:`~.report.STRICT_ERROR_CODES` 就抛异常.

        Note:
            事件先入报告再抛, 所以 ``LrcParser`` 的使用方 ``except`` 之后仍能从
            :attr:`report` 读到"到这里为止发生了什么" (包括刚触发的那条).
        """
        self._events.append(
            ParseEvent(code=code, message=message, line_no=line_no, raw_line=raw_line)
        )
        if self.options.strict and code in STRICT_ERROR_CODES:
            raise InvalidLyricsError(
                f"[{code}] {message}", line_no=line_no, raw_line=raw_line
            )

    def _emit(
        self,
        code: str,
        message: str,
        *,
        line_no: int | None = None,
        raw_line: str | None = None,
        level: int = logging.WARNING,
    ) -> None:
        """打日志并记进报告.

        日志文本由 ``Line N: `` 前缀与 `` (raw=...)`` 后缀拼出来, 拼法与重构前
        逐字一致, 免得既有的日志断言失效; 报告里则把行号 / 原始行存成独立字段.
        """
        location = f"Line {line_no}: " if line_no is not None else ""
        raw = f" (raw={raw_line!r})" if raw_line is not None else ""
        logger.log(level, f"{location}{message}{raw}")
        self._record(code, message, line_no=line_no, raw_line=raw_line)

    def _line_event_callback(self, line_no: int, raw_line: str) -> EventCallback:
        """构造给 :func:`parse_line` 用的回调: 只收集, 不打日志.

        逐字标记那几条 warning 已经由 :func:`_drop_unusable_times` 打过, 这里再打
        一遍就会重复; 报告里补上行号才是新增的价值.
        """

        def _callback(code: str, message: str) -> None:
            self._record(code, message, line_no=line_no, raw_line=raw_line)

        return _callback

    def parse_raw_line(self, line_no: int, raw_line: str) -> None:
        """处理一行原始文本 (metadata / 行标签 / 逐字标签 / 参考行 / 结束标记).

        Args:
            line_no: 行号 (从 1 开始), 用于日志与错误信息.
            raw_line: 原始行 (未去缩进).

        Raises:
            InvalidLyricsError: 行内容非法; 异常上会补好 ``line_no`` / ``raw_line``.
        """
        # 去除行首缩进以识别标签, 但保留正文尾随空白。正文空白是有效文本。
        line_str = raw_line.lstrip()
        # 逐字标记被忽略时, parse_line 只知道 code / message, 行号得由这里补.
        on_event = self._line_event_callback(line_no, raw_line)

        # 1. 若行首是时间标签 (方括号或尖括号) 则直接按歌词行处理,
        #    避免 metadata 误匹配.
        #    例如 "[00:01.000]This is by [ar:tist]" 或
        #    "<00:01.000>text [ar:Artist]" 不应被当作 metadata.
        #    但是这其实是非标行为应该是 UB, 但是就这样写了.
        #    此外 metadata 判定要求整行由 metatag 构成 (见 _extract_metadata),
        #    行中混有普通文本的 [key: value] 不会把整行吞掉.
        if (
            not self._line_tag_check.match(line_str)
            and not self._word_tag_check.match(line_str)
        ) and (meta := _extract_metadata(line_str)):
            # extend 而不是 update: 同名 key 要全部留下 ([ti: A] 与 [ti: B] 是
            # 合法的重复写法), 用 dict 语义会在这一步静默丢掉先出现的值.
            self.metadata.extend(meta)
            logger.debug(f"Metadata line {line_no}: {line_str!r}")
            return

        logger.debug(f"Parsing lyric line {line_no}: {line_str!r}")

        # 2. 切出行首的重复时间标签
        raw_lyric_line = line_str
        time_tags, line_str = _split_leading_line_timetags(line_str)

        # 正文末尾的方括号标签 (其后只剩空白) 是 SPL 的行尾时间, 它同时是逐字
        # 标记的上界: 晚于它的逐字标记一律忽略, 而不是反过来把行尾丢掉.
        line_end = _trailing_line_end_tag(line_str)

        # 2a. 行首有方括号标签、但正文里没有任何文字 (只有时间标签或空白) →
        #     SPL 的"纯结束标记": "时间戳后不接任何文本内容的行是纯粹的结束标记:
        #     它不会产生一句新歌词, 也不参与翻译识别". 于是把时间写到上一行歌词
        #     的 end 上, 而不是造一条空歌词行 —— 造空行会让紧随其后、时间戳相同
        #     的真实歌词行被挂成它的参考行 (真实语料里 138 个文件、420 行踩坑).
        #     Note: 整行不含方括号标签 (即用尖括号写出的空行) 不走这里, 见 2b.
        if time_tags and not _body_has_text(line_str):
            for tag in time_tags:
                if self._apply_line_end_marker(tag, line_no=line_no, raw_line=raw_line):
                    self._end_markers_applied += 1
            return

        # 2b. 若行首存在多个连续方括号时间标签, 且剩余正文还含有时间标签,
        #     则这些连续标签有两种读法, 用 SPL 的"逐字标记必须递增"来判定:
        #     * 整行标签非递减 → 首字延迟的逐字行 (`[行标签][首字标签]文本`) ,
        #       按完整原行解析成单行. 真实语料里 199 行有 197 行是这一形态.
        #     * 出现递减 → 折叠行 (重复行简写) , 每个行首标签各生成一行,
        #       正文里早于该行的逐字标签按 SPL 忽略.
        if len(time_tags) > 1 and compile_regex(GENERIC_TIMETAG_REGEX).search(line_str):
            if _is_non_decreasing_timetags(raw_lyric_line):
                try:
                    line = parse_line(
                        raw_lyric_line,
                        line_start=time_tags[0],
                        line_end=line_end,
                        on_event=on_event,
                    )
                except InvalidLyricsError as exc:
                    exc.line_no = exc.line_no or line_no
                    exc.raw_line = exc.raw_line or raw_line
                    raise
                if line:
                    line_start = line[0].start
                    if line_start is None:  # pragma: no cover - 正文有文字
                        raise InvalidLyricsError(
                            f"Line {line_no}: ambiguous leading time tags "
                            f"did not produce a line start; raw={raw_line!r}",
                            line_no=line_no,
                            raw_line=raw_line,
                        )
                    self._register_line_at_tags(line, [line_start])
                    self._apply_explicit_line_end([line_start], line_end)
                    self.last_tag = line_start
                    self.last_text_tags = [line_start]
            else:
                for tag in time_tags:
                    line = parse_line(
                        line_str, line_start=tag, line_end=line_end, on_event=on_event
                    )
                    if not line:  # pragma: no cover - 正文有文字, 不可能是空白
                        continue
                    registered = self._register_line_at_tags(line, [tag])
                    self._apply_explicit_line_end(registered, line_end)
                    self.last_tag = registered[0]
                    self.last_text_tags = list(registered)
            return

        try:
            line = parse_line(
                line_str,
                line_start=time_tags[0] if time_tags else None,
                line_end=line_end,
                on_event=on_event,
            )
        except InvalidLyricsError as exc:
            exc.line_no = exc.line_no or line_no
            exc.raw_line = exc.raw_line or raw_line
            raise

        # 2c. 行首没有方括号时间标签 → 要么是逐字行, 要么是参考行/分隔符
        if not time_tags:
            if not line:
                # 空分隔行, 重置参考行锚点
                self.last_tag = None
                logger.debug("Reference line marker reset")
                return
            # 若行首为逐字标签 (尖括号), 以第一个词元的 start 作为 line.start
            if line[0].start is not None:
                self._register_line_at_tags(line, [line[0].start])
                self._apply_explicit_line_end([line[0].start], line_end)
                self.last_tag = line[0].start
                # 没有正文的尖括号行 (如 "<00:01.000>") 是 LRC 家族里唯一能
                # 无歧义表达"空 cue"的写法, 保留为一条空正文行; 但它不是一句
                # 歌词, 因此不能当结束标记的收尾目标.
                if line.text:
                    self.last_text_tags = [line[0].start]
                return
            if self.last_tag is None:
                self._emit(
                    "orphaned-line",
                    f"orphaned lyric line (no anchor): {line!r}",
                    line_no=line_no,
                    raw_line=raw_line,
                )
                return
            # 防御性检查: 按当前实现, last_tag 的所有赋值路径都指向已注册的
            # 时间点, 此分支不可达; 保留以防未来改动破坏该不变量.
            if self.last_tag not in self.line_pool:  # pragma: no cover
                self._emit(
                    "orphaned-line",
                    f"reference anchor {self.last_tag}ms not in line pool, "
                    f"line treated as orphaned: {line!r}",
                    line_no=line_no,
                    raw_line=raw_line,
                )
                return
            logger.debug(
                f"Adding {line!r} as reference of {self.line_pool[self.last_tag]!r}"
            )
            self.line_pool[self.last_tag].reference_lines.append(line)
            self._reference_lines_attached += 1
            return

        # 2d. 常规行: 可能有多个重复时间标签, 每个都生成一行
        if not line:
            # parse_line 只在正文为空白时返回 None, 如 "[00:01.000]  ". 按"正文
            # 空白是有效文本"的既定取向, 这种空白算作内容; 否则 dumps()
            # 写出的 "[00:01.000]  " 无法往返.
            line = BasicLyricLine([LyricToken(content=line_str)])
        registered_tags = self._register_line_at_tags(line, time_tags)
        self._apply_explicit_line_end(registered_tags, line_end)
        # 只有真实落入 line_pool 的时间点才能作为参考行锚点, 否则后续无标签行
        # 会在 line_pool 上 KeyError.
        self.last_tag = registered_tags[0]
        self.last_text_tags = list(registered_tags)

    def finalize(self) -> Lyrics:
        """把已累积的行池排序、补全行首/行尾时间并装进 :class:`Lyrics`.

        Note:
            喂完所有行之后调用它拿到结果; :meth:`parse` 已经替你调过.
        """
        # ParseOptions.__post_init__ 已把 str 形式的 line_filter 编译为正则, 但
        # ParseOptions 是可变 dataclass, 调用方仍可能在构造之后再赋一个字符串;
        # 这里再归一化一次, 不依赖"构造后再没人改过"这一隐式前提.
        line_filter = self.options.line_filter
        if isinstance(line_filter, str):
            line_filter = re.compile(line_filter)

        return _finalize_lyrics(
            self.metadata,
            self.line_pool,
            fill_implicit_line_end=self.options.fill_implicit_line_end,
            line_filter=line_filter,
            on_event=self._record,
        )

    def _register_line_at_tags(
        self,
        line: BasicLyricLine,
        time_tags: list[int],
    ) -> list[int]:
        """把同一行歌词注册到 ``line_pool`` 中所有 ``time_tags`` 对应的时间点上.

        越界逐字标签已由 :func:`parse_line` 的 ``line_start`` / ``line_end`` 过滤
        (SPL: 逐字标记必须落在行开始与结束时间之间, 否则忽略该标记), 因此这里不再
        需要"行首标签与逐字标签矛盾时归位"的逻辑 —— 行标签始终为准.

        Returns:
            实际落入 ``line_pool`` 的时间点列表. 调用方应只把返回值中的时间点用作
            后续参考行的锚点, 否则挂载时会对未注册时间点取 KeyError.
        """
        registered: list[int] = []
        for tag in time_tags:
            if tag in self.line_pool:
                # 同一个时间点已有行 → 当前行变为参考行.
                # 必须拷贝: 同一行的多个重复时间标签可能都命中已存在的时间点,
                # 若直接 append 原实例, 多个 reference_lines 槽位会共享同一对象,
                # 改动其一会波及其它槽位.
                self.line_pool[tag].reference_lines.append(line.copy())
            else:
                # 拷贝 word 列表, 避免多个 LyricLine 共享同一 LyricToken 实例
                self.line_pool[tag] = LyricLine(start=tag, content=line.copy())
            registered.append(tag)
        return registered

    def _apply_explicit_line_end(self, tags: list[int], line_end: int | None) -> None:
        """把同行内的行尾标签写成这些行的 ``end`` (SPL 的显式行尾) .

        行尾标签通常会被解析成末词元的 ``end``, 再由
        :func:`_finalize_lyrics` 提升为行尾; 但当它与末词元时间相同时, 词元时间会被
        "重复标签"合并掉, 行尾就没了. 这里按已知的 ``line_end`` 补上, 保证
        ``[00:02.000]<00:10.000>hello[00:10.000]`` 的结束时间不丢.

        只在目标行还没有结束时间、且行首早于行尾时写入 (零长度区间不是有效区间) .
        """
        if line_end is None:
            return
        for tag in tags:
            line = self.line_pool.get(tag)
            if line is not None and line.end is None and line.start < line_end:
                line.end = line_end

    def _apply_line_end_marker(self, tag: int, *, line_no: int, raw_line: str) -> bool:
        """把"只有时间标签、没有正文"的行当作上一行歌词的结束标记 (SPL) .

        SPL: "时间戳后不接任何文本内容的行是纯粹的结束标记: 它不会产生一句新歌词,
        也不参与翻译识别". 于是这里把时间写到最近一行有正文的歌词的 ``end`` 上.

        只在目标行确实还没有显式结束时间时写入 (同行内的行尾标签优先) ; 没有可收尾
        的目标 —— 文件首行、目标行开始时间不晚于该标记、目标行已有区间 —— 就忽略
        该标记, 而不是造一条空歌词行.

        Returns:
            是否真的给某一行补上了 ``end``; ``False`` 时报告里会多一条
            ``end-marker-ignored``.
        """
        for target_tag in self.last_text_tags:
            line = self.line_pool.get(target_tag)
            if line is None or line.start >= tag:
                continue
            token_end = line.content[-1].end if line.content else None
            if line.end is not None or token_end is not None:
                logger.debug(
                    f"End marker {tag}ms ignored: the line at {line.start}ms already "
                    f"has an explicit end"
                )
                continue
            line.end = tag
            logger.debug(f"End marker: line at {line.start}ms now ends at {tag}ms")
            return True
        self._emit(
            "end-marker-ignored",
            f"End marker {tag}ms has no line to close; ignored",
            line_no=line_no,
            raw_line=raw_line,
            level=logging.DEBUG,
        )
        return False


def parse_lrc(lrc: str, *, options: ParseOptions | None = None) -> Lyrics:
    """解析一份完整的 LRC 文本.

    Args:
        lrc: LRC 源文本.
        options: 解析选项.

    Returns:
        组装完毕的 :class:`Lyrics` 对象.

    Note:
        offset 需通过 :meth:`Lyrics.apply_delta` 单独应用,
        解析时不会自动偏移时间戳.

    Note:
        只关心结果时用它; 还要知道"丢了哪些行 / 忽略了哪些标记"就用
        :func:`parse_with_report`.
    """
    return LrcParser(options).parse(lrc)


def parse_with_report(
    lrc: str, *, options: ParseOptions | None = None
) -> tuple[Lyrics, ParseReport]:
    """解析 LRC 文本, 同时返回结构化的解析报告.

    与 :func:`parse_lrc` 的结果完全一致, 只是额外给出 :class:`~.report.ParseReport`
    —— 把"哪些行被丢弃 / 哪些逐字标记被忽略 / 哪条行尾推断被丢弃"从日志变成可
    编程检查的数据. 干净文件的报告是空的 (``bool(report)`` 为 ``False``).

    Args:
        lrc: LRC 源文本.
        options: 解析选项.

    Returns:
        ``(lyrics, report)``.
    """
    parser = LrcParser(options)
    lyrics = parser.parse(lrc)
    return lyrics, parser.report


def _body_has_text(line: str) -> bool:
    """去掉所有时间标签后, ``line`` 是否还剩内容 (空白也算内容) .

    这是"这一行到底有没有正文"的判据, 也是 SPL 纯结束标记的分界线:
    ``""`` 与 ``"<00:01.000>"`` 都没有正文, 而 ``"  "`` 有 (正文空白是有效
    文本) .
    """
    return bool(compile_regex(GENERIC_TIMETAG_REGEX).sub("", line))


def _trailing_line_end_tag(line: str) -> int | None:
    """取出行末的方括号行尾标签 (SPL 的显式行尾) , 没有则返回 ``None``.

    判据是"正文里最后一个方括号标签, 且它之后只剩空白" —— SPL 规定结束时间写
    成 ``[mm:ss.xxx]``, 尖括号是逐字标记的写法; 若方括号标签后面还有正文, 它是
    逐字标记而不是行尾.
    """
    last: re.Match[str] | None = None
    for match in compile_regex(LINE_TIMETAG_REGEX).finditer(line):
        last = match
    if last is None or line[last.end() :].strip():
        return None
    return match_to_ms(last)


def _is_non_decreasing_timetags(line: str) -> bool:
    """``line`` 里所有时间标签 (方括号 + 尖括号) 是否非递减.

    SPL 要求逐字标记递增, 因此"行首标签 + 首字标签"形式的逐字行必然非递减;
    折叠行 (重复行简写) 的第二个行首标签通常晚于正文里的逐字标记, 于是出现递减.
    这个判据把 :func:`parse_lrc` 2a 分支里两种同形写法分开.
    """
    values = [
        match_to_ms(m) for m in compile_regex(GENERIC_TIMETAG_REGEX).finditer(line)
    ]
    return all(a <= b for a, b in zip(values, values[1:]))


def _finalize_lyrics(
    metadata: Metadata,
    line_pool: dict[int, LyricLine],
    *,
    fill_implicit_line_end: bool,
    line_filter: re.Pattern[str] | None = None,
    on_event: EventCallback | None = None,
) -> Lyrics:
    """把 ``line_pool`` 按时间排序、补全行首/行尾时间并装进 :class:`Lyrics`.

    Note:
        ``line_filter`` 统一为已编译的正则 (``str`` 会在 :class:`ParseOptions`
        构造时被编译), 命中 ``pattern.search`` 的行会被丢弃.

    Note:
        ``end`` 的优先级是"同行内的行尾标签 / 末词元的 ``end``" > "空行结束标记
        写下的 ``end``" > ``fill_implicit_line_end`` 的下一行开始时间. 推断出的
        ``end`` 若与行首时间矛盾 (``end <= start``, 例如行尾标签与行首标签相同),
        会被丢弃并记 warning, 而不再产出 ``end <= start`` 的行 —— 那是
        :func:`~.validation.validate_lyrics` 眼里的 error, 也会让 ``to_srt()``
        去"修正"一个本不该存在的区间. 词元自身的 ``start`` / ``end`` 原样保留.

    Args:
        on_event: 丢弃被过滤的行 / 丢弃矛盾的行尾推断时的回调 (见
            :data:`.report.ParseEventCode`). 这里拿不到源文件行号, 所以事件里
            只有毫秒时间与文本.
    """
    # 先应用过滤, 再排序填充, 保证 fill_implicit_line_end 不依赖被丢弃的行
    if line_filter is not None:
        kept: dict[int, LyricLine] = {}
        for ts, line in line_pool.items():
            if line_filter.search(line.text):
                message = f"Line at {ts}ms dropped by line_filter: {line.text!r}"
                logger.debug(message)
                if on_event is not None:
                    on_event("line-filtered", message)
                continue
            kept[ts] = line
        line_pool = kept

    lyrics = Lyrics(metadata=metadata)
    sorted_items = sorted(line_pool.items(), key=lambda kv: kv[0])

    for idx, (line_start, line) in enumerate(sorted_items):
        line.start = line_start

        # 把最后一个 word 的 end 提升为整行 end (保留词元原始值)
        inferred_end: int | None = None
        if line.content:
            inferred_end = line.content[-1].end
        if inferred_end is not None and inferred_end <= line_start:
            message = (
                f"Line at {line_start}ms: inferred line end {inferred_end}ms is "
                f"not after the line start (byword tags disagree with the line "
                f"tag); discarding the inferred end"
            )
            logger.warning(message)
            if on_event is not None:
                on_event("inferred-end-discarded", message)
            inferred_end = None
        # 推断不出 end 时保留 _apply_line_end_marker 写下的值, 不要清掉
        if inferred_end is not None:
            line.end = inferred_end

        # 可选: 用下一行的开始时间作为当前行的隐式结束
        if fill_implicit_line_end and line.end is None and idx + 1 < len(sorted_items):
            line.end = sorted_items[idx + 1][0]

        lyrics.append(line)

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
        times.append(match_to_ms(match))
        raw_line = raw_line[match.end() :]
    return times, raw_line


def _extract_metadata(line: str) -> list[tuple[str, str]]:
    """从一行字符串中提取 metadata 标签 ``[key: value]``.

    仅当**整行**都由 metatag (及其间空白) 构成时才视为 metadata 行并提取;
    正文中间出现 ``[key: value]`` 的普通文本行不会被吞并 —— 否则
    ``finditer`` 非锚定匹配会把 "Return [to: sender] now" 这类行整行当成
    metadata, 导致正文静默丢失. 这类行现在按普通歌词/参考行处理.

    ``value`` 的结束位置由**配对方括号**决定 (见
    :func:`._parse_metatag_line`), 因此 ``[al: Album [Deluxe]]`` 的 value 是
    ``Album [Deluxe]``: 这是 LRC 社区里真实存在的写法 (参见 rmpc#519), 而
    "取第一个 ``]`` 就收尾"的简单实现 (如 ffmpeg) 会把它截断成
    ``Album [Deluxe``.

    Returns:
        ``(key, value)`` 序列 (同一行里重复的 key 也原样保留), 不是 metadata
        行时返回 ``[]``. 之所以不返回 ``dict``: 那会在这一层就把同行重复的
        key 折叠掉, 后面的 :meth:`Metadata.extend` 也就无从保留.
    """
    tags = _parse_metatag_line(line)
    if tags is None:
        return []
    return tags


def _parse_metatag_line(line: str) -> list[tuple[str, str]] | None:
    """把整行解析为 metatag 序列; 整行不是纯 metatag 时返回 ``None``.

    规则 (与社区实现对比见 :func:`_extract_metadata`):

    * 行首到行尾只允许 metatag 与其间的空白, 否则整行按正文处理.
    * key 必须匹配 :data:`.regex.METATAG_KEY_REGEX`; key 与 ``:`` 两侧允许空白.
    * value 允许包含**配对平衡**的方括号: 遇到 ``[`` 深度 +1, 遇到 ``]`` 深度
      -1, 深度回到 0 的那个 ``]`` 才是本标签的结束位置. 于是
      ``[al: Album [Deluxe]]`` 得到 ``Album [Deluxe]``, 而
      ``[ti: a]extra[ar: b]`` 会在 ``extra`` 处失败 (整行不算 metadata,
      正文不会被静默吞掉).
    * value 两侧空白会被去掉.

    Returns:
        ``[(key, value), ...]``; 整行不满足规则时返回 ``None``. 同一行内重复的
        key 由调用方决定覆盖语义.
    """
    key_regex = compile_regex(METATAG_KEY_REGEX)
    tags: list[tuple[str, str]] = []
    pos = 0
    length = len(line)

    while True:
        # 标签之间的空白
        while pos < length and line[pos].isspace():
            pos += 1
        if pos >= length:
            break
        if line[pos] != "[":
            return None
        pos += 1

        # key
        while pos < length and line[pos].isspace():
            pos += 1
        key_match = key_regex.match(line, pos)
        if key_match is None:
            return None
        key = key_match.group(0)
        pos = key_match.end()

        # ':'
        while pos < length and line[pos].isspace():
            pos += 1
        if pos >= length or line[pos] != ":":
            return None
        pos += 1

        # value: 扫到配对的第一个 ']'
        value_start = pos
        depth = 0
        while pos < length:
            char = line[pos]
            if char == "[":
                depth += 1
            elif char == "]":
                if depth == 0:
                    break
                depth -= 1
            pos += 1
        if pos >= length:
            # 方括号不平衡 (比如 "[ti: a [b]"), 无法确定边界
            return None

        tags.append((key, line[value_start:pos].strip()))
        pos += 1  # 跳过 ']'

    return tags or None
