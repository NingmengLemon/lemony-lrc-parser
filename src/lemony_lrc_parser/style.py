"""源文本的书写风格.

只探测、不应用: 探测结果交给调用方, 要不要沿用由调用方显式传进
:class:`~.models.SerializationOptions` 决定. 解析结果 (:class:`~.models.Lyrics`)
本身不记录风格, 因为风格是源文本的属性, 不是歌词数据的属性.

Note:
    Python 的文本模式读文件 (``open(path)`` / ``Path.read_text()`` 的默认值)
    会把 ``\\r\\n`` 转成 ``\\n``, 探测到的永远是 ``"lf"``. 要拿到真实的行尾,
    读的时候传 ``newline=""``, 或者按二进制读再自己解码.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "DetectedLineEnding",
    "LineEnding",
    "detect_line_ending",
]

#: 可写出的行尾风格.
LineEnding = Literal["lf", "crlf"]

#: :func:`detect_line_ending` 的结果. ``"mixed"`` 不能直接用于写出, 调用方得自己
#: 决定怎么处理.
DetectedLineEnding = Literal["lf", "crlf", "mixed"]


def detect_line_ending(text: str) -> DetectedLineEnding | None:
    """探测 ``text`` 的行尾风格.

    Returns:
        ``"lf"`` / ``"crlf"``: 全文只用这一种.
        ``"mixed"``: 两种都有, 或出现了单独的 ``\\r`` (老式 Mac 风格, 解析器照样
        能按行切开, 但写不出来).
        ``None``: 全文没有换行.
    """
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if cr or (crlf and lf):
        return "mixed"
    if crlf:
        return "crlf"
    if lf:
        return "lf"
    return None
