"""时间标签处理工具.

集中管理 LRC 时间标签 (``[mm:ss.xxx]`` / ``<mm:ss.xxx>``) 的解析与格式化.
"""

from __future__ import annotations

from logging import getLogger

from ._utils import match_to_ms
from .exceptions import ProgrammingError, TimestampUnderflowError
from .regex import LINE_TIMETAG_REGEX, compile_regex

logger = getLogger(__name__)

MIN_TAIL_DIGITS: int = 1
MAX_TAIL_DIGITS: int = 6

__all__ = [
    "format_timetag",
    "parse_timetag",
]


def format_timetag(
    ms: int,
    *,
    use_angle_bracket: bool,
    tail_digits: int,
) -> str:
    """将毫秒数格式化为 LRC 时间标签字符串.

    Args:
        ms: 毫秒时间戳 (不允许为负) .
        use_angle_bracket: True 使用 ``<...>`` (逐字标签) , False 使用 ``[...]`` (行标签) .
        tail_digits: 毫秒尾部补齐的位数.

    Returns:
        形如 ``[01:23.456]`` 或 ``<01:23.456>`` 的字符串.
    """
    if ms < 0:
        raise TimestampUnderflowError(f"Negative timestamp is not allowed: {ms}ms")
    if not MIN_TAIL_DIGITS <= tail_digits <= MAX_TAIL_DIGITS:
        raise ProgrammingError(
            f"tail_digits must be between {MIN_TAIL_DIGITS} and {MAX_TAIL_DIGITS}, got {tail_digits}"
        )
    minutes = ms // 60_000
    seconds = (ms % 60_000) // 1000
    millis = ms % 1000

    if tail_digits > 3:
        # 小数位数 > 3 时, 尾部需要填入更多精度位 (零填充),
        # 例如 123ms / tail_digits=4 → tail=1230
        tail = millis * 10 ** (tail_digits - 3)
    elif tail_digits < 3:
        # 小数位数 < 3 时, tail 分别表示十分秒 (1 位) 或百分秒 (2 位),
        # 而非毫秒, 需要截断转换
        tail = millis // 10 ** (3 - tail_digits)
    else:
        tail = millis

    body = f"{minutes:02d}:{seconds:02d}.{tail:0{tail_digits}d}"
    return f"<{body}>" if use_angle_bracket else f"[{body}]"


def parse_timetag(s: str) -> int | None:
    """解析一个时间标签字符串, 返回对应毫秒数.

    支持 ``[mm:ss.xxx]`` (三段齐全) 或 ``[mm:ss]`` (省略毫秒部分) 格式,
    与解析器的行为保持一致. 也可解析 ``<mm:ss.xxx>`` 等通用格式.
    解析失败返回 ``None``.
    """
    # 使用 LINE_TIMETAG_REGEX (而非 TIMETAG_REGEX_STRICT) 以与解析器行为一致.
    # 前者允许省略毫秒、1-6 位尾数、行内空白.
    match = compile_regex(rf"^{LINE_TIMETAG_REGEX}$").match(s)
    return match_to_ms(match) if match else None
