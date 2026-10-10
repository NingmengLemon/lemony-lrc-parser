"""解析报告与序列化报告.

把解析 / 序列化过程中"丢了什么 / 忽略了什么 / 改了什么"从日志变成结构化数据: 日志
适合人排查, 报告适合程序消费 (CLI 输出、审计、上游重试、strict 模式的判定依据).

* :class:`ParseReport`: :func:`~.parser.parse_with_report` 给出, 位置是源文件行号.
* :class:`DumpReport`: :func:`~.serializer.dump_with_report` 给出, 位置是
  :class:`~.models.Lyrics` 里的行下标 (写出时没有源文件可言).

事件代码 (``ParseEvent.code``) 与 :class:`~.validation.ValidationIssue` 的错误码
同属一套 kebab-case 命名, 后续 strict 模式复用同一批代码, 不再另立枚举.

Note:
    报告只收**值得调用方知道**的事件 (丢弃 / 忽略 / 修正), 正常操作不进去:
    被挂成参考行、被结束标记正常收尾这类只记在
    :attr:`ParseReport.reference_lines_attached` / :attr:`ParseReport.end_markers_applied`
    这两个计数里. 所以干净文件的报告是空的, ``bool(report)`` 为 ``False``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "DROPPED_LINE_CODES",
    "LOSSY_DUMP_CODES",
    "STRICT_ERROR_CODES",
    "DumpEvent",
    "DumpEventCode",
    "DumpReport",
    "ParseEvent",
    "ParseEventCode",
    "ParseReport",
]


#: 已知的事件代码. 只是提示: 报告不限制 ``code`` 的取值 (与 metadata key 同一取向).
#:
#: * ``orphaned-line``: 无锚点又无时间标签的行, 整行丢弃.
#: * ``line-filtered``: 被 ``ParseOptions.line_filter`` 丢掉的行.
#: * ``byword-before-line-start`` / ``byword-after-line-end``: 越界的逐字标记,
#:   标记被忽略, 两侧文本合并.
#: * ``byword-unordered``: 乱序 (递减) 的逐字标记, 同样被忽略.
#: * ``end-marker-ignored``: 纯结束标记找不到可收尾的上一行.
#: * ``inferred-end-discarded``: 由逐字标签推断出的行尾与行首矛盾, 推断被丢弃.
ParseEventCode = Literal[
    "orphaned-line",
    "line-filtered",
    "byword-before-line-start",
    "byword-after-line-end",
    "byword-unordered",
    "end-marker-ignored",
    "inferred-end-discarded",
]

#: 表示"这一行没有进入解析结果"的代码, 供 :attr:`ParseReport.dropped_lines` 使用.
DROPPED_LINE_CODES: frozenset[str] = frozenset({"orphaned-line", "line-filtered"})

#: strict 模式 (:class:`~.models.ParseOptions` 的 ``strict=True``) 下会直接抛
#: :class:`~.exceptions.InvalidLyricsError` 的代码.
#:
#: 判据是"解析器不得不丢掉或忽略文件里的某个声明": 孤儿行整行没了, 逐字标记 / 结束
#: 标记 / 行尾推断被忽略. 两类刻意不在其中:
#:
#: * ``line-filtered``: 那是调用方自己要求丢的, 不是文件的问题.
#: * metadata key 与 ``offset`` 的问题 (由 :meth:`~.models.Lyrics.validate` 报告):
#:   它们不影响解析结果, 放进 strict 只会把"本来能正常解析的文件"判死.
STRICT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "orphaned-line",
        "byword-before-line-start",
        "byword-after-line-end",
        "byword-unordered",
        "end-marker-ignored",
        "inferred-end-discarded",
    }
)


@dataclass(frozen=True)
class ParseEvent:
    """解析过程中的一条事件.

    Attributes:
        code: 事件代码, 见 :data:`ParseEventCode`.
        message: 人类可读的描述 (英文, 与运行时日志口径一致).
        line_no: 源文件行号 (从 1 开始), 未知时为 ``None``.
        raw_line: 出错行的原始文本, 未知时为 ``None``.

    Note:
        由 :func:`~.parser.parse_line` 内部产生的逐字标记事件, 其日志仍按原格式
        (不带行号) 输出, 但报告里会补上 ``line_no`` / ``raw_line`` —— 这两个字段
        由调用 ``parse_line`` 的一方填, 它才知道行号.
    """

    code: str
    message: str
    line_no: int | None = None
    raw_line: str | None = None


@dataclass(frozen=True)
class ParseReport:
    """一次解析的结构化报告.

    Attributes:
        events: 值得注意的事件, 按发生顺序.
        reference_lines_attached: 被挂成参考行的行数 (正常操作, 只计数).
        end_markers_applied: 成功收尾的纯结束标记个数 (正常操作, 只计数).
    """

    events: tuple[ParseEvent, ...] = ()
    reference_lines_attached: int = 0
    end_markers_applied: int = 0

    def __len__(self) -> int:
        """事件条数 (不是行数; 计数见两个属性)."""
        return len(self.events)

    def __iter__(self) -> Iterator[ParseEvent]:
        return iter(self.events)

    def __bool__(self) -> bool:
        """是否有值得注意的事件; 干净文件为 ``False``."""
        return bool(self.events)

    def of_code(self, code: str) -> list[ParseEvent]:
        """取出指定代码的全部事件, 按发生顺序."""
        return [event for event in self.events if event.code == code]

    @property
    def dropped_lines(self) -> list[ParseEvent]:
        """整行没有进入结果的事件 (孤儿行 / 被 ``line_filter`` 丢掉的行)."""
        return [event for event in self.events if event.code in DROPPED_LINE_CODES]


#: 序列化事件的已知代码. 与 :data:`ParseEventCode` 一样只是提示, 不限制取值.
#:
#: * ``bracket-first-tag-splits-line``: ``use_bracket_for_byword_tag=True`` 下延迟的
#:   首词元写成 ``[行首][首字]正文``, 后面没有可区分的标签, 重新解析会读成两行、
#:   正文重复.
#: * ``bracket-first-tag-adds-token``: 同一写法, 但后面还有标签, 重新解析仍是一行,
#:   行首多一个零文本词元. 正文与时间不丢.
#: * ``byword-out-of-range-omitted``: 逐字标记落在行的 ``[start, end]`` 之外, 解析端
#:   按 SPL 会忽略它, 所以不写出.
#: * ``textless-reference-skipped``: 没有正文的参考行 LRC 表达不了, 不写出.
#: * ``metadata-key-unparsable``: metadata key 不符合解析规则, 重新解析时丢失.
#: * ``metadata-value-unbalanced``: value 里方括号不配对, 重新解析时整行变成正文.
#: * ``metadata-value-newline``: value 含换行, 会破坏 metadata 行结构.
DumpEventCode = Literal[
    "bracket-first-tag-splits-line",
    "bracket-first-tag-adds-token",
    "byword-out-of-range-omitted",
    "textless-reference-skipped",
    "metadata-key-unparsable",
    "metadata-value-unbalanced",
    "metadata-value-newline",
]

#: 重新解析读不回原数据的序列化事件. 只有 ``bracket-first-tag-adds-token`` 不在其中:
#: 它改变了词元结构 (多一个空词元), 但正文与所有时间都还在.
LOSSY_DUMP_CODES: frozenset[str] = frozenset(
    {
        "bracket-first-tag-splits-line",
        "byword-out-of-range-omitted",
        "textless-reference-skipped",
        "metadata-key-unparsable",
        "metadata-value-unbalanced",
        "metadata-value-newline",
    }
)


@dataclass(frozen=True)
class DumpEvent:
    """序列化过程中的一条事件.

    Attributes:
        code: 事件代码, 见 :data:`DumpEventCode`.
        message: 人类可读的描述 (英文, 与运行时日志口径一致).
        line_index: 涉事行在 ``lyrics`` 中的下标, metadata 事件为 ``None``.
        reference_index: 涉事参考行在 ``line.reference_lines`` 中的下标; 主行或
            metadata 事件为 ``None``.
        metadata_key: metadata 事件的 key, 其它事件为 ``None``.
    """

    code: str
    message: str
    line_index: int | None = None
    reference_index: int | None = None
    metadata_key: str | None = None


@dataclass(frozen=True)
class DumpReport:
    """一次序列化的结构化报告. 能无损写出的歌词报告为空 (``bool(report)`` 为假).

    Attributes:
        events: 事件, 按写出顺序.
    """

    events: tuple[DumpEvent, ...] = ()

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self) -> Iterator[DumpEvent]:
        return iter(self.events)

    def __bool__(self) -> bool:
        return bool(self.events)

    def of_code(self, code: str) -> list[DumpEvent]:
        """取出指定代码的全部事件, 按发生顺序."""
        return [event for event in self.events if event.code == code]

    @property
    def lossy(self) -> list[DumpEvent]:
        """重新解析读不回原数据的事件 (见 :data:`LOSSY_DUMP_CODES`)."""
        return [event for event in self.events if event.code in LOSSY_DUMP_CODES]
