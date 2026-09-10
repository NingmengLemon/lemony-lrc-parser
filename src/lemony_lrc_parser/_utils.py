"""内部工具函数.

集中存放跨模块共享、但不属于公共 API 的小工具. 本模块不对外暴露,
以下划线前缀命名, 外部不应依赖.
"""

from __future__ import annotations

import re
import sys
from logging import getLogger

logger = getLogger(__name__)

__all__ = [
    "DC_SLOTS",
    "is_bracket_balanced",
    "match_to_ms",
]

#: 供包内 dataclass 复用的 ``slots`` 参数 (按解释器版本降级).
#:
#: ``slots`` 自 3.10 起可用, ``weakref_slot`` 自 3.11 起可用; 3.9 下为空 dict.
#: 集中在 :mod:`._utils` 里定义, 避免各模块重复同一份版本判断.
DC_SLOTS: dict[str, bool] = (
    {"slots": True, "weakref_slot": True}
    if sys.version_info >= (3, 11)
    else {"slots": True}
    if sys.version_info >= (3, 10)
    else {}
)


def match_to_ms(match: re.Match[str]) -> int:
    """从时间标签正则匹配对象中提取毫秒数.

    兼容两类命名组:

    * 标准命名组 ``min`` / ``sec`` / ``tail`` (见 ``LINE_TIMETAG_REGEX`` 等) .
    * 前缀命名组 ``line_min`` / ``word_min`` 等 (见 ``GENERIC_TIMETAG_REGEX``) .

    Note:
        解析策略偏宽松: 秒数超过 59 (如 ``[00:99.000]``) 不会报错, 而是按字面值
        折算并产生一条 warning 日志, 与"宽松解析 + 可诊断"的整体取向一致.
    """
    groups = match.groupdict()

    # 优先使用前缀命名组, 再退回到标准命名组
    min_val = groups.get("line_min") or groups.get("word_min") or groups.get("min")
    sec_val = groups.get("line_sec") or groups.get("word_sec") or groups.get("sec")
    tail_val = groups.get("line_tail") or groups.get("word_tail") or groups.get("tail")

    minutes = int(min_val or 0)
    seconds = int(sec_val or 0)

    if seconds >= 60:
        logger.warning(
            f"Time tag {match.group(0)!r} has seconds >= 60 "
            f"(treated literally as {seconds * 1000}ms)"
        )

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


def is_bracket_balanced(text: str) -> bool:
    """``text`` 里的方括号是否全部配对 (嵌套也算).

    这是 metadata value 能否往返的判据: 解析端用"配对方括号"确定 value 的边界
    (见 :func:`~.parser._parse_metatag_line`), 因此只有配对的 value 才能被原样
    读回; 不配对的写法 (如 ``[ti: 50% ]off]``) 要么提前收尾、要么找不到边界,
    重新解析时整行都不再是 metadata.

    Note:
        该函数只看方括号的配对, 不负责其它往返障碍 (换行、非法 key 等).
    """
    depth = 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            if depth == 0:
                return False
            depth -= 1
    return depth == 0
