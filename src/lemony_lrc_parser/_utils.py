"""内部工具函数.

集中存放跨模块共享、但不属于公共 API 的小工具. 本模块不对外暴露,
以下划线前缀命名, 外部不应依赖.
"""

from __future__ import annotations

import re

__all__ = [
    "match_to_ms",
]


def match_to_ms(match: re.Match[str]) -> int:
    """从时间标签正则匹配对象中提取毫秒数.

    兼容两类命名组:

    * 标准命名组 ``min`` / ``sec`` / ``tail`` (见 ``LINE_TIMETAG_REGEX`` 等) .
    * 前缀命名组 ``line_min`` / ``word_min`` 等 (见 ``GENERIC_TIMETAG_REGEX``) .
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
