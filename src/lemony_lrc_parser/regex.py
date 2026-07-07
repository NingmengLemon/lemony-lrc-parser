"""正则表达式常量与编译缓存.

本模块集中存放 LRC 语法所需的正则模式, 并提供带缓存的 :func:`compile_regex`.
这些常量会被 :mod:`.parser`、:mod:`.timetag` 等模块消费, 不建议外部直接依赖.
"""

from __future__ import annotations

import re

__all__ = [
    "GENERIC_TIMETAG_REGEX",
    "LINE_TIMETAG_REGEX",
    "METATAG_REGEX",
    "WORD_TIMETAG_REGEX",
    "compile_regex",
]

_REGEX_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def compile_regex(pattern: str) -> re.Pattern[str]:
    """使用 ``re.VERBOSE`` 编译正则, 并以模式字符串为 key 做进程级缓存."""
    compiled = _REGEX_PATTERN_CACHE.get(pattern)
    if compiled is None:
        compiled = re.compile(pattern, flags=re.VERBOSE)
        _REGEX_PATTERN_CACHE[pattern] = compiled
    return compiled


def _make_timetag_regex(open_char: str, close_char: str, prefix: str = "") -> str:
    """按括号符号和命名组前缀生成一段时间标签子模式.

    行标签 (``[mm:ss.xxx]``) 与逐字标签 (``<mm:ss.xxx>``) 的结构完全一致,
    只有括号符号与命名组前缀不同, 因此统一由本函数生成, 避免复制粘贴漂移.

    Args:
        open_char: 起始括号 (已转义), 如 ``r"\\["`` 或 ``r"\\<"``.
        close_char: 结束括号 (已转义), 如 ``r"\\]"`` 或 ``r"\\>"``.
        prefix: 命名组前缀, 用于在 :data:`GENERIC_TIMETAG_REGEX` 中避免
            同名组冲突 (如 ``"line_"`` / ``"word_"``); 空串表示无前缀.
    """
    return rf"""
    (?:
        {open_char}
            \s*
                (?P<{prefix}min>\d{{1,4}})
            \s*
            :
            \s*
                (?P<{prefix}sec>\d{{1,2}})
            \s*
            (?:
                [:\.]
                \s*
                    (?P<{prefix}tail>\d{{1,6}})
                \s*
            )?
        {close_char}
    )
    """


#: 行时间标签 ``[mm:ss.xxx]``, 命名组: ``min`` / ``sec`` / ``tail``.
LINE_TIMETAG_REGEX: str = _make_timetag_regex(r"\[", r"\]")

#: 逐字时间标签 ``<mm:ss.xxx>``, 命名组: ``min`` / ``sec`` / ``tail``.
WORD_TIMETAG_REGEX: str = _make_timetag_regex(r"\<", r"\>")


#: 元数据标签 ``[key: value]``, 命名组: ``key`` / ``value``.
METATAG_REGEX: str = r"""
    (?:
        \[
            \s*
            (?P<key>[a-zA-Z][a-zA-Z0-9]{1,15})
            \s*
            :
            \s*
            (?P<value>.*?)
            \s*
        \]
    )
"""

#: 通用时间标签 (同时匹配方括号行标签与尖括号逐字标签) .
#:
#: 为避免同名命名组冲突, 方括号分支使用 ``line_*`` 前缀,
#: 尖括号分支使用 ``word_*`` 前缀. 消费方应使用 :func:`._utils.match_to_ms` 抹平差异.
GENERIC_TIMETAG_REGEX: str = (
    "(?:"
    + _make_timetag_regex(r"\[", r"\]", prefix="line_")
    + "|"
    + _make_timetag_regex(r"\<", r"\>", prefix="word_")
    + ")"
)
