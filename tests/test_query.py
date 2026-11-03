"""测试 query 模块的时间范围查询与搜索委托."""

from __future__ import annotations

import pytest

from lemony_lrc_parser import (
    BasicLyricLine,
    LyricLine,
    Lyrics,
    LyricToken,
    ProgrammingError,
)
from lemony_lrc_parser.query import (
    contains_regex,
    contains_text,
    find_regex,
    find_text,
    lines_in_range,
)


def _line(
    start: int,
    text: str,
    end: int | None = None,
    references: tuple[str, ...] = (),
) -> LyricLine:
    return LyricLine(
        start=start,
        end=end,
        content=BasicLyricLine([LyricToken(content=text)]),
        reference_lines=[
            BasicLyricLine([LyricToken(content=reference)]) for reference in references
        ],
    )


class TestLinesInRange:
    def test_explicit_ranges_overlap(self) -> None:
        lyrics = Lyrics(
            [_line(0, "a", 1000), _line(1000, "b", 2000), _line(2000, "c", 3000)]
        )
        assert [line.text for line in lines_in_range(lyrics, 500, 1500)] == ["a", "b"]
        assert [line.text for line in lines_in_range(lyrics, 1000, 1000)] == ["a", "b"]

    def test_boundaries_are_inclusive(self) -> None:
        lyrics = Lyrics([_line(1000, "a", 2000)])
        assert [line.text for line in lines_in_range(lyrics, 1000, 1000)] == ["a"]
        assert [line.text for line in lines_in_range(lyrics, 2000, 2000)] == ["a"]

    def test_implicit_end_uses_next_start(self) -> None:
        lyrics = Lyrics([_line(0, "a"), _line(1000, "b", 2000), _line(3000, "c", 4000)])
        assert [line.text for line in lines_in_range(lyrics, 500, 800)] == ["a"]
        assert [line.text for line in lines_in_range(lyrics, 1500, 2500)] == ["b"]
        assert [line.text for line in lines_in_range(lyrics, 1200, 1800)] == ["b"]
        # 0 的行按下一行 start=1000 推断 end, 与查询区间只在 1000 点相交
        assert [line.text for line in lines_in_range(lyrics, 1000, 1500)] == [
            "a",
            "b",
        ]

    def test_last_implicit_end_extends_to_query_end(self) -> None:
        lyrics = Lyrics([_line(0, "a", 1000), _line(2000, "b")])
        assert [line.text for line in lines_in_range(lyrics, 2500, 3000)] == ["b"]
        assert lines_in_range(lyrics, 1001, 1999) == []

    def test_empty(self) -> None:
        assert lines_in_range(Lyrics(), 0, 1000) == []

    def test_invalid_range(self) -> None:
        with pytest.raises(ProgrammingError):
            lines_in_range(Lyrics([_line(0, "a")]), 1000, 500)

    def test_reference_lines_are_not_separate(self) -> None:
        lyrics = Lyrics([_line(1000, "a", 2000, references=("翻译",))])
        hits = lines_in_range(lyrics, 1000, 2000)
        assert [line.text for line in hits] == ["a"]
        assert hits[0].reference_lines[0].text == "翻译"

    def test_unsorted_input_is_handled(self) -> None:
        lyrics = Lyrics([_line(2000, "b", 3000), _line(0, "a", 1000)])
        assert [line.text for line in lines_in_range(lyrics, 0, 2500)] == ["b", "a"]

    def test_duplicate_starts_use_next_distinct_start(self) -> None:
        lyrics = Lyrics([_line(1000, "a"), _line(1000, "b"), _line(2000, "c", 3000)])
        # 前两行都没有 end, 按下一个不同的 start=2000 推断
        assert [line.text for line in lines_in_range(lyrics, 1500, 1800)] == [
            "a",
            "b",
        ]


class TestSearchDelegation:
    def test_methods_delegate(self) -> None:
        lyrics = Lyrics([_line(0, "hello"), _line(1000, "world", references=("你好",))])
        assert lyrics.contains_text("你好")
        assert [line.text for line in lyrics.find_text("hello")] == ["hello"]
        assert lyrics.contains_regex(r"w.rld")
        assert [line.text for line in lyrics.find_regex("^你")] == ["world"]

    def test_module_functions(self) -> None:
        lyrics = Lyrics([_line(0, "hello")])
        assert contains_text(lyrics, "ell")
        assert [line.text for line in find_text(lyrics, "ell")] == ["hello"]
        assert contains_regex(lyrics, "h.l")
        assert [line.text for line in find_regex(lyrics, "h.l")] == ["hello"]

    def test_lines_in_range_method_delegates(self) -> None:
        lyrics = Lyrics([_line(0, "a", 1000)])
        assert [line.text for line in lyrics.lines_in_range(0, 1000)] == ["a"]
