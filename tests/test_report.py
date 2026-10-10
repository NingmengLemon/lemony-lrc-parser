"""测试解析报告与 strict 模式.

报告只收"值得调用方知道"的事件 (丢弃 / 忽略 / 修正), 正常操作只计数, 所以干净文件
的报告是空的 —— 这一条是整组用例的前提, 先钉住它, 免得以后有人把 debug 级日志也
塞进来, 让 ``bool(report)`` 失去意义.

strict 模式直接定义在这套事件代码上 (:data:`~lemony_lrc_parser.report.STRICT_ERROR_CODES`),
所以放在同一个文件里, 改一处时不容易漏掉另一处.
"""

from __future__ import annotations

import pytest

from lemony_lrc_parser import (
    InvalidLyricsError,
    Lyrics,
    LyricsParserError,
    ParseEvent,
    ParseOptions,
    ParseReport,
    parse_line,
    parse_lrc,
    parse_with_report,
    validate_lyrics,
)
from lemony_lrc_parser.parser import LrcParser
from lemony_lrc_parser.report import STRICT_ERROR_CODES, ParseEventCode

CLEAN = "[ti: T]\n[00:01.000]a\n[00:02.000]b\n"

#: 每个 strict 错误代码对应的最小输入 (键是期望的事件代码).
STRICT_TRIGGERS: dict[str, str] = {
    "orphaned-line": "[00:01.000]a\n\norphan\n",
    "byword-before-line-start": "[00:05.000]<00:01.000>a<00:06.000>b\n",
    "byword-after-line-end": "[00:01.000]a<00:05.000>b[00:02.000]\n",
    "byword-unordered": "[00:01.000]a<00:03.000>b<00:02.000>c\n",
    "inferred-end-discarded": "[00:01.000]text[00:01.000]\n",
}


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
        """``parse_line(on_event=...)`` 直接可用, 默认仍然是只打日志.

        回调收的是 ``ParseEvent``; ``parse_line`` 不知道行号, 两个位置字段为空.
        """
        seen: list[ParseEvent] = []
        parse_line(
            "[00:05.000]<00:01.000>a",
            line_start=5000,
            on_event=seen.append,
        )
        assert [event.code for event in seen] == ["byword-before-line-start"]
        assert all(isinstance(event, ParseEvent) for event in seen)
        assert seen[0].line_no is None
        assert seen[0].raw_line is None
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

    @pytest.mark.parametrize(
        ("text", "reason"),
        [
            ("[00:00.300]\n[00:01.000]a\n", "no lyric line before it"),
            ("[00:05.000]a\n[00:05.000]\n", "not after the start"),
            ("[00:01.000]a[00:02.000]\n[00:03.000]\n", "already ends at another time"),
        ],
    )
    def test_ignored_marker_says_why(self, text: str, reason: str) -> None:
        _, report = parse_with_report(text)
        (event,) = report
        assert event.code == "end-marker-ignored"
        assert reason in event.message

    @pytest.mark.parametrize(
        "text",
        [
            "[00:01.000]a[00:02.000]\n[00:02.000]\n",  # 与同行行尾重合
            "[00:01.000]a\n[00:02.000]\n[00:02.000]\n",  # 同一个标记连写两遍
            "[00:01.000]a<00:02.000>\n[00:02.000]\n",  # 与末词元的 end 重合
        ],
    )
    def test_redundant_marker_is_counted_not_reported(self, text: str) -> None:
        lyrics, report = parse_with_report(text)
        assert not report
        assert report.end_markers_redundant == 1
        assert lyrics[0].end == 2000

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
        assert parser.report.end_markers_redundant == 0
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


class TestStrictMode:
    """``ParseOptions(strict=True)``: 不再丢 / 忽略文件里的声明, 当场抛异常."""

    def test_default_is_lenient(self) -> None:
        """默认宽松: 上面每个触发输入都能正常解析出结果."""
        for code, text in STRICT_TRIGGERS.items():
            lyrics, report = parse_with_report(text)
            assert code in _codes(report), code
            assert isinstance(lyrics, Lyrics)

    def test_clean_file_passes(self) -> None:
        assert len(parse_lrc(CLEAN, options=ParseOptions(strict=True))) == 2

    @pytest.mark.parametrize(("code", "text"), sorted(STRICT_TRIGGERS.items()))
    def test_each_code_raises(self, code: str, text: str) -> None:
        with pytest.raises(InvalidLyricsError) as exc_info:
            parse_lrc(text, options=ParseOptions(strict=True))
        error = exc_info.value
        assert f"[{code}]" in str(error)
        # 可被 LyricsParserError 捕获 (异常层级不变)
        assert isinstance(error, LyricsParserError)

    def test_line_info_is_attached_when_available(self) -> None:
        with pytest.raises(InvalidLyricsError) as exc_info:
            parse_lrc(
                STRICT_TRIGGERS["orphaned-line"], options=ParseOptions(strict=True)
            )
        assert exc_info.value.line_no == 3
        assert exc_info.value.raw_line == "orphan"

    def test_inferred_end_has_no_line_number(self) -> None:
        """行尾推断发生在 finalize 阶段, 拿不到源文件行号 —— 已知代价."""
        with pytest.raises(InvalidLyricsError) as exc_info:
            parse_lrc(
                STRICT_TRIGGERS["inferred-end-discarded"],
                options=ParseOptions(strict=True),
            )
        assert exc_info.value.line_no is None
        assert "1000ms" in str(exc_info.value)  # 毫秒信息仍在

    def test_end_markers_never_raise(self) -> None:
        """被忽略的结束标记只丢一个时间点, 不丢正文, strict 不该管."""
        text = "[00:00.300]\n[00:01.000]a[00:02.000]\n[00:03.000]\n[00:03.000]\n"
        lyrics = parse_lrc(text, options=ParseOptions(strict=True))
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (1000, 2000, "a")
        ]
        assert "end-marker-ignored" not in STRICT_ERROR_CODES

    def test_line_filter_never_raises(self) -> None:
        """``line_filter`` 丢掉的行是调用方自己要求的, strict 不该管."""
        options = ParseOptions(strict=True, line_filter="drop")
        lyrics = parse_lrc("[00:01.000]keep\n[00:02.000]drop me\n", options=options)
        assert [line.text for line in lyrics] == ["keep"]

    def test_metadata_issues_are_left_to_validate(self) -> None:
        """``offset`` 不可解析不影响解析结果, 归 ``validate()``, 不进 strict."""
        text = "[offset: abc]\n[00:01.000]a\n"
        lyrics = parse_lrc(text, options=ParseOptions(strict=True))
        assert lyrics.metadata["offset"] == "abc"
        assert [issue.code for issue in validate_lyrics(lyrics)] == ["offset-not-int"]

    def test_report_survives_the_raise(self) -> None:
        """事件先入报告再抛, 所以 catch 之后仍能读到发生了什么."""
        parser = LrcParser(ParseOptions(strict=True))
        with pytest.raises(InvalidLyricsError):
            parser.parse(STRICT_TRIGGERS["orphaned-line"])
        assert _codes(parser.report) == ["orphaned-line"]

    def test_strict_stops_at_the_first_violation(self) -> None:
        """严格模式是"当场拒绝", 不是"收完所有再汇总"."""
        text = "[00:01.000]a\n\norphan one\n\norphan two\n"
        parser = LrcParser(ParseOptions(strict=True))
        with pytest.raises(InvalidLyricsError) as exc_info:
            parser.parse(text)
        assert exc_info.value.line_no == 3
        assert _codes(parser.report) == ["orphaned-line"]  # 只到第一条

    def test_manual_feeding_raises_too(self) -> None:
        """逐步喂行时同样当场拒绝 (无锚点的行)."""
        parser = LrcParser(ParseOptions(strict=True))
        with pytest.raises(InvalidLyricsError):
            parser.parse_raw_line(1, "orphan text")

    def test_strict_code_set_is_a_subset_of_known_codes(self) -> None:
        """strict 不能引用未登记的事件代码."""
        known = set(ParseEventCode.__args__)
        assert known >= STRICT_ERROR_CODES
        assert "line-filtered" not in STRICT_ERROR_CODES
