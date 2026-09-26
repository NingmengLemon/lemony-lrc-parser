"""测试解析报告 (:mod:`lemony_lrc_parser.report`).

报告只收"值得调用方知道"的事件 (丢弃 / 忽略 / 修正), 正常操作只计数, 所以干净文件
的报告是空的 —— 这一条是整组用例的前提, 先钉住它, 免得以后有人把 debug 级日志也
塞进来, 让 ``bool(report)`` 失去意义.
"""

from __future__ import annotations

from lemony_lrc_parser import (
    Lyrics,
    ParseOptions,
    ParseReport,
    parse_line,
    parse_lrc,
    parse_with_report,
)
from lemony_lrc_parser.parser import LrcParser

CLEAN = "[ti: T]\n[00:01.000]a\n[00:02.000]b\n"


def _codes(report: ParseReport) -> list[str]:
    return [event.code for event in report]


class TestReportBasics:
    """干净文件 / 等价性 / 容器语义."""

    def test_clean_file_has_empty_report(self) -> None:
        _, report = parse_with_report(CLEAN)
        assert not report
        assert len(report) == 0
        assert list(report) == []
        assert report.reference_lines_attached == 0
        assert report.end_markers_applied == 0

    def test_result_matches_parse_lrc(self) -> None:
        lyrics, _ = parse_with_report(CLEAN)
        assert lyrics == parse_lrc(CLEAN)

    def test_options_are_honoured(self) -> None:
        lyrics, _ = parse_with_report(
            "[00:01.000]a\n[00:02.000]b\n",
            options=ParseOptions(fill_implicit_line_end=True),
        )
        assert [line.end for line in lyrics] == [2000, None]

    def test_report_is_an_immutable_snapshot(self) -> None:
        """``events`` 是 tuple, 拿到手的报告不会被解析器后续动作改掉."""
        parser = LrcParser()
        parser.parse("[00:01.000]a\n\norphan\n")
        report = parser.report
        assert isinstance(report.events, tuple)

        parser.parse("[00:02.000]b\n\nanother orphan\n")

        assert _codes(report) == ["orphaned-line"]
        assert len(parser.report) == 1

    def test_of_code_filters(self) -> None:
        _, report = parse_with_report("[00:01.000]a\n\norphan\n")
        assert report.of_code("orphaned-line") == list(report)
        assert report.of_code("nope") == []


class TestDroppedLines:
    """整行没有进入结果的事件."""

    def test_orphaned_line(self) -> None:
        _, report = parse_with_report("[00:01.000]a\n\norphan text\n")
        assert _codes(report) == ["orphaned-line"]
        event = report.dropped_lines[0]
        assert event.line_no == 3
        assert event.raw_line == "orphan text"
        assert "orphaned lyric line" in event.message

    def test_line_filter(self) -> None:
        _, report = parse_with_report(
            "[00:01.000]keep\n[00:02.000]drop me\n",
            options=ParseOptions(line_filter="drop"),
        )
        assert _codes(report) == ["line-filtered"]
        event = report.dropped_lines[0]
        assert "drop me" in event.message

    def test_orphaned_line_is_not_attached_as_reference(self) -> None:
        """没有锚点时整行丢弃, 不会被当成参考行 —— 计数也不该动."""
        _, report = parse_with_report("[00:01.000]a\n\norphan\n")
        assert report.reference_lines_attached == 0


class TestBywordEvents:
    """逐字标记被忽略时的三类事件 (由 parse_line 回调上报)."""

    def test_before_line_start(self) -> None:
        _, report = parse_with_report("[00:05.000]<00:01.000>a<00:06.000>b\n")
        assert "byword-before-line-start" in _codes(report)
        assert report.of_code("byword-before-line-start")[0].line_no == 1

    def test_after_line_end(self) -> None:
        _, report = parse_with_report("[00:01.000]a<00:05.000>b[00:02.000]\n")
        assert "byword-after-line-end" in _codes(report)

    def test_unordered(self) -> None:
        _, report = parse_with_report("[00:01.000]a<00:03.000>b<00:02.000>c\n")
        assert "byword-unordered" in _codes(report)

    def test_equal_tags_are_not_an_event(self) -> None:
        """``now == prev`` 是逐字行里的正常写法, 不进报告."""
        _, report = parse_with_report("[00:01.000]a<00:02.000>b<00:02.000>c\n")
        assert _codes(report) == []

    def test_parse_line_callback_is_public(self) -> None:
        """``parse_line(on_event=...)`` 直接可用, 默认仍然是只打日志."""
        seen: list[tuple[str, str]] = []
        parse_line(
            "[00:05.000]<00:01.000>a",
            line_start=5000,
            on_event=lambda code, message: seen.append((code, message)),
        )
        assert [code for code, _ in seen] == ["byword-before-line-start"]
        # 不传回调时不报错, 行为照旧
        assert parse_line("[00:05.000]<00:01.000>a", line_start=5000) is not None


class TestStructuralEvents:
    """结束标记与行尾推断相关的事件 / 计数."""

    def test_end_marker_applied_is_counted_not_reported(self) -> None:
        lyrics, report = parse_with_report("[00:01.000]a\n[00:02.000]\n")
        assert lyrics[0].end == 2000
        assert report.end_markers_applied == 1
        assert not report  # 正常收尾不算事件

    def test_end_marker_ignored(self) -> None:
        _, report = parse_with_report("[00:01.000]a\n[00:02.000]\n[00:03.000]\n")
        assert _codes(report) == ["end-marker-ignored"]
        assert report.of_code("end-marker-ignored")[0].line_no == 3
        assert report.end_markers_applied == 1

    def test_inferred_end_discarded(self) -> None:
        _, report = parse_with_report("[00:01.000]text[00:01.000]\n")
        assert _codes(report) == ["inferred-end-discarded"]
        # finalize 阶段拿不到源文件行号
        assert report.of_code("inferred-end-discarded")[0].line_no is None

    def test_reference_lines_are_counted(self) -> None:
        lyrics, report = parse_with_report("[00:01.000]a\n翻译\n[00:02.000]b\n")
        assert lyrics[0].reference_lines[0].text == "翻译"
        assert report.reference_lines_attached == 1
        assert not report  # 挂参考行是正常操作

    def test_counts_reset_with_the_parser(self) -> None:
        parser = LrcParser()
        parser.parse("[00:01.000]a\n翻译\n[00:02.000]\n")
        assert parser.report.reference_lines_attached == 1
        assert parser.report.end_markers_applied == 1

        parser.reset()

        assert parser.report.reference_lines_attached == 0
        assert parser.report.end_markers_applied == 0
        assert not parser.report

    def test_report_is_available_after_manual_feeding(self) -> None:
        parser = LrcParser()
        for line_no, raw_line in enumerate("[00:01.000]a\n\norphan\n".splitlines(), 1):
            parser.parse_raw_line(line_no, raw_line)
        parser.finalize()
        assert _codes(parser.report) == ["orphaned-line"]


class TestMixedDocument:
    """一份同时踩到多种情况的文件, 事件按发生顺序排列."""

    def test_event_order(self) -> None:
        text = (
            "[00:01.000]a\n"
            "\n"
            "orphan\n"
            "[00:02.000]b\n"
            "翻译\n"
            "[00:03.000]\n"
            "[00:04.000]\n"
            "[00:05.000]c<00:06.000>d<00:05.500>e\n"
            "[00:07.000]f[00:07.000]\n"
        )
        lyrics, report = parse_with_report(text)
        assert _codes(report) == [
            "orphaned-line",
            "end-marker-ignored",
            "byword-unordered",
            "inferred-end-discarded",
        ]
        assert [event.line_no for event in report.dropped_lines] == [3]
        assert report.reference_lines_attached == 1
        assert report.end_markers_applied == 1
        assert [line.text for line in lyrics] == ["a", "b", "cde", "f"]

    def test_lyrics_are_unaffected_by_reporting(self) -> None:
        """开不开报告, 解析结果都一样."""
        text = "[00:01.000]a\n\norphan\n[00:02.000]b\n"
        assert parse_with_report(text)[0] == parse_lrc(text)
        assert isinstance(parse_lrc(text), Lyrics)
