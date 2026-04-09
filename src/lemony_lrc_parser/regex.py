from __future__ import annotations

import re
from logging import getLogger
from typing import Any, TypeGuard

logger = getLogger(__name__)

_REGEX_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def compile_regex(r: str) -> re.Pattern[str]:
    if r not in _REGEX_PATTERN_CACHE:
        _REGEX_PATTERN_CACHE[r] = re.compile(r, flags=re.VERBOSE)
    return _REGEX_PATTERN_CACHE[r]


# Base time tag component (without capture groups, for composition)
_TIMETAG_COMPONENT = r"""
(?:
    \s*
        (?:\d{1,4})  
    \s*       
    :  
    \s*
        (?:\d{1,2})   
    \s*
    (?:
        [:\.]
        \s*
            (?:\d{1,6}) 
        \s*
    )?
)
"""

compile_regex(
    LINE_TIMETAG_REGEX := r"""
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
)
compile_regex(
    WORD_TIMETAG_REGEX := r"""
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
)
compile_regex(
    TIMETAG_REGEX_STRICT := r"""
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
)
compile_regex(
    METATAG_REGEX := r"""
    (?:
        \[
            \s*
            (?P<key>[a-zA-Z#]{2,16}) # # is for comments, see https://en.wikipedia.org/wiki/LRC_(file_format)
            \s*
            :
            \s*
            (?P<value>.+?)
            \s*
        \]
    )
"""
)
# Generic time tag: use non-capturing group version to avoid duplicate named group issues
compile_regex(
    GENERIC_TIMETAG_REGEX := r"""
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
)


def is_match(obj: Any) -> TypeGuard[re.Match[str]]:
    return isinstance(obj, re.Match)


def is_str(obj: Any) -> TypeGuard[str]:
    return isinstance(obj, str)
