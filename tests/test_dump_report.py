"""测试序列化报告 (:func:`~lemony_lrc_parser.dump_with_report`).

与解析报告对称: 干净的歌词报告为空; 每种有损或会改变结构的写出各有一个事件代码,
位置是 ``lyrics`` 里的行下标 (写出时没有源文件行号). 事件与日志一一对应, 所以
消费方把日志静音后仍能从报告里拿到同样的信息.
"""

from __future__ import annotations

import logging

import pytest

from lemony_lrc_parser import (
    BasicLyricLine,
    DumpReport,
    LyricLine,
    Lyrics,
    LyricToken,
    SerializationOptions,
    dump_with_report,
)
from lemony_lrc_parser.report import LOSSY_DUMP_CODES

BRACKET = SerializationOptions(use_bracket_for_byword_tag=True)


def _tok(content: str, start: int | None = None, end: int | None = None) -> LyricToken:
    return LyricToken(content=content, start=start, end=end)


def _line(
    start: int,
    end: int | None,
    tokens: list[LyricToken],
    refs: list[BasicLyricLine] | None = None,
) -> LyricLine:
    return LyricLine(
        start=start,
        end=end,
        content=BasicLyricLine(tokens),
        reference_lines=refs or [],
    )


def _codes(report: DumpReport) -> list[str]:
    return [event.code for event in report]


class TestCleanDump:
    def test_clean_lyrics_have_an_empty_report(self) -> None:
        lyrics = Lyrics.loads("[ti: T]\n[00:01.000]a<00:01.500>b[00:02.000]\n翻译\n")
        text, report = dump_with_report(lyrics)
        assert text == lyrics.dumps()
        assert not report
        assert len(report) == 0
        assert report.lossy == []

    def test_text_is_identical_to_dumps(self) -> None:
        """报告只是附带的, 写出的文本与 ``dumps`` 一字不差."""
        lyrics = Lyrics(
            [_line(1000, 2000, [_tok("a", 1000, 1500), _tok("b", 1500, 2600)])]
        )
        assert dump_with_report(lyrics, options=BRACKET)[0] == lyrics.dumps(
            options=BRACKET
        )


class TestBywordOutOfRange:
    """越界的逐字标记不写出; 这一处此前连日志都没有."""

    def test_after_line_end(self, caplog: pytest.LogCaptureFixture) -> None:
        lyrics = Lyrics(
            [_line(1000, 2000, [_tok("a", 1000, 1500), _tok("b", 1500, 2600)])]
        )
        with caplog.at_level(logging.WARNING, logger="lemony_lrc_parser.serializer"):
            text, report = dump_with_report(lyrics)
        assert text == "[00:01.000]a<00:01.500>b[00:02.000]\n"
        assert _codes(report) == ["byword-out-of-range-omitted"]
        assert report.events[0].line_index == 0
        assert "2600ms" in report.events[0].message
        assert "byword-out-of-range" not in caplog.text  # 日志里不出现代码
        assert "2600ms" in caplog.text  # 但同一条信息也进了日志

    def test_before_line_start(self) -> None:
        lyrics = Lyrics(
            [_line(1000, 2000, [_tok("a", 500, 1500), _tok("b", 1500, 2000)])]
        )
        _, report = dump_with_report(lyrics)
        assert _codes(report) == ["byword-out-of-range-omitted"]
        assert "500ms" in report.events[0].message

    def test_shared_boundary_is_reported_once(self) -> None:
        """相邻词元共享的越界时间点只算一次."""
        lyrics = Lyrics(
            [_line(1000, 2000, [_tok("a", 1000, 2500), _tok("b", 2500, 2600)])]
        )
        _, report = dump_with_report(lyrics)
        (event,) = report
        assert "2500ms, 2600ms" in event.message

    def test_one_event_per_line(self) -> None:
        lyrics = Lyrics(
            [
                _line(1000, 2000, [_tok("a", 1000, 2600)]),
                _line(3000, 4000, [_tok("b", 3000, 4500)]),
            ]
        )
        _, report = dump_with_report(lyrics)
        assert [event.line_index for event in report] == [0, 1]


class TestReferenceLines:
    def test_textless_reference_line_is_skipped(self) -> None:
        lyrics = Lyrics(
            [
                _line(
                    1000,
                    None,
                    [_tok("x")],
                    refs=[
                        BasicLyricLine([_tok("ok")]),
                        BasicLyricLine([_tok("", 1000, 1200)]),
                    ],
                )
            ]
        )
        text, report = dump_with_report(lyrics)
        assert text == "[00:01.000]x\n[00:01.000]ok\n"
        (event,) = report
        assert event.code == "textless-reference-skipped"
        assert (event.line_index, event.reference_index) == (0, 1)

    def test_empty_text_line_with_references_is_reported(self) -> None:
        """空正文行带参考行: 空 cue 不当宿主, 读回时参考行升为正文, 记有损事件.

        这正是 0.4.x 把"空行 + 同时间戳的歌词"读出来的形状.
        """
        lyrics = Lyrics(
            [
                _line(1000, 1800, [_tok("")], refs=[BasicLyricLine([_tok("tr")])]),
                _line(2000, None, [_tok("x")]),
            ]
        )
        text, report = dump_with_report(lyrics)
        assert _codes(report) == ["empty-line-references"]
        assert report.events[0].line_index == 0
        assert report.lossy == list(report)
        reparsed = Lyrics.loads(text)
        assert [(line.start, line.text) for line in reparsed] == [
            (1000, "tr"),
            (2000, "x"),
        ]
        assert reparsed[0].reference_lines == []


class TestBracketFirstTag:
    def test_splits_line(self) -> None:
        lyrics = Lyrics.loads("[00:01.000]<00:01.500>hello\n")
        _, report = dump_with_report(lyrics, options=BRACKET)
        assert _codes(report) == ["bracket-first-tag-splits-line"]
        assert report.lossy == list(report)

    def test_adds_token_is_reported_but_not_lossy(self) -> None:
        lyrics = Lyrics.loads("[00:01.000]<00:01.500>hello[00:03.000]\n")
        _, report = dump_with_report(lyrics, options=BRACKET)
        assert _codes(report) == ["bracket-first-tag-adds-token"]
        assert report.lossy == []

    def test_reference_line_index(self) -> None:
        lyrics = Lyrics.loads("[00:01.000]x\n[00:01.000]<00:01.500>ref\n")
        _, report = dump_with_report(lyrics, options=BRACKET)
        (event,) = report
        assert event.code == "bracket-first-tag-splits-line"
        assert (event.line_index, event.reference_index) == (0, 0)

    def test_default_angle_brackets_have_no_event(self) -> None:
        lyrics = Lyrics.loads("[00:01.000]<00:01.500>hello\n")
        assert not dump_with_report(lyrics)[1]


class TestMetadata:
    @pytest.mark.parametrize(
        ("key", "value", "code"),
        [
            ("#c", "v", "metadata-key-unparsable"),
            ("ti", "50% ]off", "metadata-value-unbalanced"),
            ("ar", "a\nb", "metadata-value-newline"),
        ],
    )
    def test_each_check_has_its_code(self, key: str, value: str, code: str) -> None:
        lyrics = Lyrics([_line(1000, None, [_tok("x")])], metadata={key: value})
        _, report = dump_with_report(lyrics)
        (event,) = report
        assert event.code == code
        assert event.metadata_key == key
        assert event.line_index is None

    def test_without_metadata_nothing_is_checked(self) -> None:
        lyrics = Lyrics([_line(1000, None, [_tok("x")])], metadata={"#c": "v"})
        _, report = dump_with_report(
            lyrics, options=SerializationOptions(with_metadata=False)
        )
        assert not report


class TestReportApi:
    def test_of_code_and_iteration(self) -> None:
        lyrics = Lyrics(
            [
                _line(1000, 2000, [_tok("a", 1000, 2600)]),
                _line(3000, None, [_tok("x")], refs=[BasicLyricLine([_tok("")])]),
            ],
            metadata={"#c": "v"},
        )
        _, report = dump_with_report(lyrics)
        assert _codes(report) == [
            "metadata-key-unparsable",
            "byword-out-of-range-omitted",
            "textless-reference-skipped",
        ]
        assert [e.line_index for e in report.of_code("textless-reference-skipped")] == [
            1
        ]
        assert len(report.lossy) == 3

    def test_lossy_codes_exclude_only_the_structural_one(self) -> None:
        from typing import get_args

        from lemony_lrc_parser import DumpEventCode

        assert set(get_args(DumpEventCode)) - LOSSY_DUMP_CODES == {
            "bracket-first-tag-adds-token"
        }
