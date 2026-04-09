"""正则表达式常量与编译缓存.

本模块集中存放 LRC 语法所需的正则模式，并提供带缓存的 :func:`compile_regex`。
这些常量会被 :mod:`.parser`、:mod:`.timetag` 等模块消费，不建议外部直接依赖。
"""

from __future__ import annotations

import re

__all__ = [
    "GENERIC_TIMETAG_REGEX",
    "LINE_TIMETAG_REGEX",
    "METATAG_REGEX",
    "TIMETAG_REGEX_STRICT",
    "WORD_TIMETAG_REGEX",
    "compile_regex",
]

_REGEX_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def compile_regex(pattern: str) -> re.Pattern[str]:
    """使用 ``re.VERBOSE`` 编译正则，并以模式字符串为 key 做进程级缓存。"""
    compiled = _REGEX_PATTERN_CACHE.get(pattern)
    if compiled is None:
        compiled = re.compile(pattern, flags=re.VERBOSE)
        _REGEX_PATTERN_CACHE[pattern] = compiled
    return compiled


# --- LRC 时间标签模式 --------------------------------------------------------

#: 行时间标签 ``[mm:ss.xxx]``，命名组：``min`` / ``sec`` / ``tail``。
LINE_TIMETAG_REGEX: str = r"""
    (?:
        \[
            \s*
                (?P<min>\d{1,4})
            \s*
            :
            \s*
                (?P<sec>\d{1,2})
            \s*
            (?:
                [:\.]
                \s*
                    (?P<tail>\d{1,6})
                \s*
            )?
        \]
    )
"""

#: 逐字时间标签 ``<mm:ss.xxx>``，命名组：``min`` / ``sec`` / ``tail``。
WORD_TIMETAG_REGEX: str = r"""
    (?:
        \<
            \s*
                (?P<min>\d{1,4})
            \s*
            :
            \s*
                (?P<sec>\d{1,2})
            \s*
            (?:
                [:\.]
                \s*
                    (?P<tail>\d{1,6})
                \s*
            )?
        \>
    )
"""

#: 严格行时间标签 ``[mm:ss.xxx]``，要求三段齐全、毫秒 1-3 位、无多余空白。
TIMETAG_REGEX_STRICT: str = r"""
    (?:
        \[
            (?P<min>\d{1,4})
            :
            (?P<sec>\d{1,2})
            \.
            (?P<tail>\d{1,3})
        \]
    )
"""

#: 元数据标签 ``[key: value]``，命名组：``key`` / ``value``。
METATAG_REGEX: str = r"""
    (?:
        \[
            \s*
            (?P<key>[a-zA-Z#]{2,16})  # `#` 用于注释标签，见 LRC 规范
            \s*
            :
            \s*
            (?P<value>.+?)
            \s*
        \]
    )
"""

#: 通用时间标签（同时匹配方括号行标签与尖括号逐字标签）。
#:
#: 为避免同名命名组冲突，方括号分支使用 ``line_*`` 前缀，
#: 尖括号分支使用 ``word_*`` 前缀。消费方应使用 :func:`._match_to_ms` 抹平差异。
GENERIC_TIMETAG_REGEX: str = r"""
    (?:
        (?:
            \[
                \s*
                    (?P<line_min>\d{1,4})
                \s*
                :
                \s*
                    (?P<line_sec>\d{1,2})
                \s*
                (?:
                    [:\.]
                    \s*
                        (?P<line_tail>\d{1,6})
                    \s*
                )?
            \]
        )
        |
        (?:
            \<
                \s*
                    (?P<word_min>\d{1,4})
                \s*
                :
                \s*
                    (?P<word_sec>\d{1,2})
                \s*
                (?:
                    [:\.]
                    \s*
                        (?P<word_tail>\d{1,6})
                    \s*
                )?
            \>
        )
    )
"""


def _warmup_cache() -> None:
    """在模块导入期预热编译缓存，避免首次使用时的抖动."""
    for pattern in (
        LINE_TIMETAG_REGEX,
        WORD_TIMETAG_REGEX,
        TIMETAG_REGEX_STRICT,
        METATAG_REGEX,
        GENERIC_TIMETAG_REGEX,
    ):
        compile_regex(pattern)


_warmup_cache()
