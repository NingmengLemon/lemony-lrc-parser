"""测试 subtitle 模块: SRT / WebVTT 与 LRC 的互转."""

from __future__ import annotations

import lemony_lrc_parser as llp
from lemony_lrc_parser.models import (
    BasicLyricLine,
    LyricLine,
    Lyrics,
    LyricToken,
    SubtitleOptions,
)
from lemony_lrc_parser.subtitle import (
    _format_ts,
    _parse_ts,
    dump_srt,
    dump_webvtt,
    parse_srt,
    parse_webvtt,
)


def _make_lyrics() -> Lyrics:
    lyrics = Lyrics()
    lyrics.lines = [
        LyricLine(
            start=1000,
            end=3000,
            content=BasicLyricLine([LyricToken(content="Hello world")]),
        ),
        LyricLine(
            start=3000,
            end=6500,
            content=BasicLyricLine([LyricToken(content="Second line")]),
        ),
    ]
    return lyrics


class TestTimestampHelpers:
    """测试时间戳格式化与解析."""

    def test_format_srt_sep(self) -> None:
        assert _format_ts(3_661_500, sep=",") == "01:01:01,500"

    def test_format_webvtt_sep(self) -> None:
        assert _format_ts(3_661_500, sep=".") == "01:01:01.500"

    def test_format_zero(self) -> None:
        assert _format_ts(0, sep=",") == "00:00:00,000"

    def test_parse_with_hours_comma(self) -> None:
        assert _parse_ts("01:01:01,500") == 3_661_500

    def test_parse_with_hours_dot(self) -> None:
        assert _parse_ts("01:01:01.500") == 3_661_500

    def test_parse_without_hours(self) -> None:
        assert _parse_ts("01:01.500") == 61_500

    def test_parse_short_millis(self) -> None:
        # "5" 补齐为 500ms
        assert _parse_ts("00:00:01.5") == 1500

    def test_roundtrip_ts(self) -> None:
        for ms in (0, 1, 999, 1000, 61_500, 3_661_500):
            assert _parse_ts(_format_ts(ms, sep=",")) == ms
            assert _parse_ts(_format_ts(ms, sep=".")) == ms


class TestDumpSrt:
    """测试 LRC → SRT."""

    def test_basic_structure(self) -> None:
        result = dump_srt(_make_lyrics())
        assert "1\n00:00:01,000 --> 00:00:03,000\nHello world" in result
        assert "2\n00:00:03,000 --> 00:00:06,500\nSecond line" in result

    def test_fill_end_from_next(self) -> None:
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(start=1000, content=BasicLyricLine([LyricToken(content="a")])),
            LyricLine(start=4000, content=BasicLyricLine([LyricToken(content="b")])),
        ]
        result = dump_srt(lyrics)
        # 第一行没有 end, 用下一行 start=4000 填充
        assert "00:00:01,000 --> 00:00:04,000" in result

    def test_default_duration_for_last_line(self) -> None:
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(start=1000, content=BasicLyricLine([LyricToken(content="a")])),
        ]
        result = dump_srt(lyrics, options=SubtitleOptions(default_duration_ms=2000))
        # 最后一行没有下一行, 用 start + default_duration
        assert "00:00:01,000 --> 00:00:03,000" in result

    def test_reference_lines_included(self) -> None:
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                end=2000,
                content=BasicLyricLine([LyricToken(content="Hello")]),
                reference_lines=[BasicLyricLine([LyricToken(content="你好")])],
            ),
        ]
        result = dump_srt(lyrics)
        assert "Hello\n你好" in result

    def test_reference_lines_excluded(self) -> None:
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                end=2000,
                content=BasicLyricLine([LyricToken(content="Hello")]),
                reference_lines=[BasicLyricLine([LyricToken(content="你好")])],
            ),
        ]
        result = dump_srt(
            lyrics, options=SubtitleOptions(include_reference_lines=False)
        )
        assert "你好" not in result


class TestDumpWebVtt:
    """测试 LRC → WebVTT."""

    def test_header(self) -> None:
        result = dump_webvtt(_make_lyrics())
        assert result.startswith("WEBVTT\n\n")

    def test_dot_separator(self) -> None:
        result = dump_webvtt(_make_lyrics())
        assert "00:00:01.000 --> 00:00:03.000" in result
        # WebVTT 不使用序号
        assert "\n1\n" not in result


class TestParseSrt:
    """测试 SRT → LRC."""

    def test_basic(self) -> None:
        srt = (
            "1\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "Hello world\n"
            "\n"
            "2\n"
            "00:00:03,000 --> 00:00:06,500\n"
            "Second line\n"
        )
        lyrics = parse_srt(srt)
        assert len(lyrics.lines) == 2
        assert lyrics.lines[0].start == 1000
        assert lyrics.lines[0].end == 3000
        assert lyrics.lines[0].text == "Hello world"
        assert lyrics.lines[1].start == 3000
        assert lyrics.lines[1].end == 6500
        assert lyrics.lines[1].text == "Second line"

    def test_multiline_cue(self) -> None:
        srt = "1\n00:00:01,000 --> 00:00:03,000\nHello\n你好\n"
        lyrics = parse_srt(srt)
        assert lyrics.lines[0].text == "Hello"
        assert len(lyrics.lines[0].reference_lines) == 1
        assert lyrics.lines[0].reference_lines[0].text == "你好"

    def test_sorted_by_start(self) -> None:
        srt = (
            "1\n00:00:05,000 --> 00:00:06,000\nlate\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\nearly\n"
        )
        lyrics = parse_srt(srt)
        assert lyrics.lines[0].text == "early"
        assert lyrics.lines[1].text == "late"


class TestParseWebVtt:
    """测试 WebVTT → LRC."""

    def test_basic(self) -> None:
        vtt = (
            "WEBVTT\n"
            "\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "Hello world\n"
            "\n"
            "00:00:03.000 --> 00:00:06.500\n"
            "Second line\n"
        )
        lyrics = parse_webvtt(vtt)
        assert len(lyrics.lines) == 2
        assert lyrics.lines[0].start == 1000
        assert lyrics.lines[0].end == 3000
        assert lyrics.lines[0].text == "Hello world"

    def test_skips_note_and_cue_id(self) -> None:
        vtt = (
            "WEBVTT\n"
            "\n"
            "NOTE this is a comment\n"
            "\n"
            "cue-1\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "text\n"
        )
        lyrics = parse_webvtt(vtt)
        assert len(lyrics.lines) == 1
        assert lyrics.lines[0].text == "text"
        assert lyrics.lines[0].start == 1000

    def test_cue_with_settings(self) -> None:
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000 align:start position:10%\ntext\n"
        lyrics = parse_webvtt(vtt)
        assert len(lyrics.lines) == 1
        assert lyrics.lines[0].end == 2000


class TestRoundtrip:
    """测试 LRC ↔ 字幕 往返一致性."""

    def test_srt_roundtrip(self) -> None:
        original = _make_lyrics()
        srt = dump_srt(original)
        restored = parse_srt(srt)
        assert len(restored.lines) == len(original.lines)
        for a, b in zip(original.lines, restored.lines):
            assert a.start == b.start
            assert a.end == b.end
            assert a.text == b.text

    def test_webvtt_roundtrip(self) -> None:
        original = _make_lyrics()
        vtt = dump_webvtt(original)
        restored = parse_webvtt(vtt)
        assert len(restored.lines) == len(original.lines)
        for a, b in zip(original.lines, restored.lines):
            assert a.start == b.start
            assert a.end == b.end
            assert a.text == b.text


class TestLyricsMethods:
    """测试 Lyrics 上的字幕方法与顶层导出."""

    def test_to_srt_method(self) -> None:
        lyrics = _make_lyrics()
        assert lyrics.to_srt() == dump_srt(lyrics)

    def test_to_webvtt_method(self) -> None:
        lyrics = _make_lyrics()
        assert lyrics.to_webvtt() == dump_webvtt(lyrics)

    def test_from_srt_classmethod(self) -> None:
        srt = "1\n00:00:01,000 --> 00:00:02,000\nhi\n"
        lyrics = Lyrics.from_srt(srt)
        assert lyrics.lines[0].text == "hi"

    def test_from_webvtt_classmethod(self) -> None:
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n"
        lyrics = Lyrics.from_webvtt(vtt)
        assert lyrics.lines[0].text == "hi"

    def test_top_level_exports(self) -> None:
        assert hasattr(llp, "dump_srt")
        assert hasattr(llp, "dump_webvtt")
        assert hasattr(llp, "parse_srt")
        assert hasattr(llp, "parse_webvtt")
        assert hasattr(llp, "SubtitleOptions")

    def test_lrc_to_srt_via_loads(self) -> None:
        lrc = "[00:01.000]Hello\n[00:03.000]World\n"
        lyrics = llp.loads(lrc)
        srt = lyrics.to_srt()
        assert "Hello" in srt
        assert "00:00:01,000 -->" in srt
