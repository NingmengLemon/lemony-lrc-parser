"""时间标签处理工具.

集中管理 LRC 时间标签 (``[mm:ss.xxx]`` / ``<mm:ss.xxx>``) 的解析与格式化.
"""

from __future__ import annotations

import re
from logging import getLogger

from .regex import TIMETAG_REGEX_STRICT, compile_regex

logger = getLogger(__name__)

__all__ = [
    "format_timetag",
    "parse_timetag",
]


def format_timetag(
    ms: int,
    *,
    use_angle_bracket: bool = False,
    tail_digits: int = 3,
) -> str:
    """将毫秒数格式化为 LRC 时间标签字符串.

    Args:
        ms: 毫秒时间戳 (允许为负, 调用方应自行保证语义合理) .
        use_angle_bracket: True 使用 ``<...>`` (逐字标签) , False 使用 ``[...]`` (行标签) .
        tail_digits: 毫秒尾部补齐的位数, 默认为 3.

    Returns:
        形如 ``[01:23.456]`` 或 ``<01:23.456>`` 的字符串.
    """
    if ms < 0:
        raise ValueError(f"Negative timestamp is not allowed: {ms}ms")
    minutes = ms // 60_000
    seconds = (ms % 60_000) // 1000
    millis = ms % 1000
    body = f"{minutes:02d}:{seconds:02d}.{millis:0{tail_digits}d}"
    return f"<{body}>" if use_angle_bracket else f"[{body}]"


def parse_timetag(s: str) -> int | None:
    """解析一个严格格式的时间标签字符串, 返回对应毫秒数.

    严格格式要求形如 ``[mm:ss.xxx]`` (方括号、三段齐全、毫秒 1-3 位) .
    解析失败返回 ``None``.
    """
    match = compile_regex(rf"^{TIMETAG_REGEX_STRICT}$").match(s)
    return _match_to_ms(match) if match else None


def _match_to_ms(match: re.Match[str]) -> int:
    """从正则匹配对象中提取毫秒数.

    兼容两类命名组:

    * 标准命名组 ``min`` / ``sec`` / ``tail`` (见 ``LINE_TIMETAG_REGEX`` 等) .
    * 前缀命名组 ``line_min`` / ``word_min`` 等 (见 ``GENERIC_TIMETAG_REGEX``) .

    该函数是包内部工具, 不导出到公共 API.
    """
    groups = match.groupdict()

    # 优先使用前缀命名组, 再退回到标准命名组
    min_val = groups.get("line_min") or groups.get("word_min") or groups.get("min")
    sec_val = groups.get("line_sec") or groups.get("word_sec") or groups.get("sec")
    tail_val = groups.get("line_tail") or groups.get("word_tail") or groups.get("tail")

    minutes = int(min_val or 0)
    seconds = int(sec_val or 0)

    if tail_val:
        # 将毫秒标准化到 3 位
        if len(tail_val) > 3:
            tail_val = tail_val[:3]  # 截断: "123456" -> "123"
        elif len(tail_val) < 3:
            tail_val = tail_val.ljust(3, "0")  # 补齐: "1" -> "100"
        millis = int(tail_val)
    else:
        millis = 0

    return millis + seconds * 1000 + minutes * 60_000
