"""异常类型.

本模块定义库内使用的异常层级. 与解析/数据本身相关的错误都继承自
:class:`LyricsParserError`; 而 :class:`ProgrammingError` 刻意**不**继承它,
用于区分"库使用者的编程错误 (传参不合法等)"与"输入数据的问题".
"""

from __future__ import annotations


class LyricsParserError(Exception):
    """所有与歌词解析/数据相关错误的基类.

    捕获本异常即可覆盖库在处理歌词数据时抛出的全部错误 (不含
    :class:`ProgrammingError`).
    """


class InvalidLyricsError(LyricsParserError):
    """输入的歌词文本结构非法, 无法被正确解析.

    Attributes:
        line_no: 出错的源文件行号 (从 1 开始), 未知时为 ``None``.
        raw_line: 出错行的原始文本, 未知时为 ``None``.
    """

    def __init__(
        self,
        message: str = "",
        *,
        line_no: int | None = None,
        raw_line: str | None = None,
    ) -> None:
        super().__init__(message)
        self.line_no = line_no
        self.raw_line = raw_line


class TimestampUnderflowError(LyricsParserError):
    """时间戳下溢: 出现了负的时间戳 (通常由过大的负向偏移导致)."""


class ProgrammingError(Exception):
    """库使用者的编程错误 (如传入非法的选项参数).

    刻意继承自 :class:`Exception` 而非 :class:`LyricsParserError`: 这类错误
    源于调用方代码的缺陷, 而非歌词数据本身的问题, 因此不应被捕获歌词错误的
    ``except LyricsParserError`` 一并吞掉, 以便尽早暴露 bug.
    """
