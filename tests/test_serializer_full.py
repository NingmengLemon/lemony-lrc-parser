"""测试 serializer 模块的完整功能."""

from __future__ import annotations

import pytest

from lemony_lrc_parser.models import LyricLine, Lyrics, LyricWord
from lemony_lrc_parser.serializer import dump_lrc


class TestDumpLrcReferenceLines:
    """测试 reference_lines 的序列化."""

    def test_reference_lines_output(self) -> None:
        """测试参考行在输出中."""
        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=[LyricWord(content="Main", start=1000)],
            reference_lines=[
                [LyricWord(content="翻译", start=1000)],
            ],
        )
        lyrics.lines = [line]

        result = dump_lrc(lyrics)
        assert "[00:01.000]Main" in result
        assert "[00:01.000]翻译" in result

    def test_multiple_reference_lines(self) -> None:
        """测试多个参考行."""
        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=[LyricWord(content="Main")],
            reference_lines=[
                [LyricWord(content="翻译1")],
                [LyricWord(content="翻译2")],
            ],
        )
        lyrics.lines = [line]

        result = dump_lrc(lyrics)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "Main" in lines[0]
        assert "翻译1" in lines[1]
        assert "翻译2" in lines[2]

    def test_reference_lines_with_byword_tags(self) -> None:
        """测试带逐字标签的参考行."""
        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=[LyricWord(content="Main")],
            reference_lines=[
                [
                    LyricWord(content="逐", start=1000, end=1100),
                    LyricWord(content="字", start=1100, end=1200),
                ],
            ],
        )
        lyrics.lines = [line]

        result = dump_lrc(lyrics, use_bracket_for_byword_tag=False)
        # 参考行也应该使用尖括号（行首是方括号，逐字标签是尖括号）
        assert "[00:01.000]逐<00:01.100>字<00:01.200>" in result
        assert "<00:01.100>" in result


class TestDumpLrcLineWithoutStart:
    """测试没有 start 的行处理."""

    def test_skip_line_without_start(self, caplog: pytest.LogCaptureFixture) -> None:
        """测试跳过没有开始时间的行."""
        import logging

        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(start=None, content=[LyricWord(content="No start")]),
            LyricLine(start=1000, content=[LyricWord(content="Has start")]),
        ]

        with caplog.at_level(logging.WARNING):
            result = dump_lrc(lyrics)

        assert "Skipping line with unknown start time" in caplog.text
        assert "No start" not in result
        assert "Has start" in result


class TestDumpLrcEmptyLyrics:
    """测试空歌词的序列化."""

    def test_empty_lyrics(self) -> None:
        """测试空歌词对象."""
        lyrics = Lyrics()
        result = dump_lrc(lyrics)
        assert result == ""

    def test_empty_lyrics_with_metadata(self) -> None:
        """测试只有 metadata 的空歌词."""
        lyrics = Lyrics()
        lyrics.metadata = {"ti": "Test", "ar": "Artist"}
        result = dump_lrc(lyrics, with_metadata=True)
        assert "[ti: Test]" in result
        assert "[ar: Artist]" in result


class TestDumpLrcBywordFormatting:
    """测试逐字标签的格式化."""

    def test_byword_with_brackets(self) -> None:
        """测试使用方括号的逐字标签."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=[
                    LyricWord(content="逐", start=1000, end=1100),
                    LyricWord(content="字", start=1100, end=1200),
                ],
            ),
        ]

        result = dump_lrc(lyrics, use_bracket_for_byword_tag=True)
        # 应该使用方括号
        assert "[00:01.000]逐" in result
        assert "[00:01.100]字" in result

    def test_byword_with_angle_brackets(self) -> None:
        """测试使用尖括号的逐字标签."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=[
                    LyricWord(content="逐", start=1000, end=1100),
                    LyricWord(content="字", start=1100, end=1200),
                ],
            ),
        ]

        result = dump_lrc(lyrics, use_bracket_for_byword_tag=False)
        # 行首使用方括号，逐字标签使用尖括号
        # 第一个词的开始时间等于行开始时间，所以不输出逐字标签
        assert "[00:01.000]逐<00:01.100>字<00:01.200>" in result
        assert "<00:01.100>字" in result

    def test_omit_redundant_start_tag(self) -> None:
        """测试省略与行首重复的开始标签."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=[
                    LyricWord(content="第", start=1000, end=1100),
                    LyricWord(content="一", start=1100, end=1200),
                ],
            ),
        ]

        result = dump_lrc(lyrics)
        # 第一个词的开始时间等于行开始时间，不应该重复输出
        assert result.count("[00:01.000]") == 1  # 只有行首标签

    def test_omit_continuous_tags(self) -> None:
        """测试省略与前一词结束时间相接的标签."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=[
                    LyricWord(content="第", start=1000, end=1100),
                    LyricWord(content="一", start=1100, end=1200),
                    LyricWord(content="个", start=1200, end=1300),
                ],
            ),
        ]

        result = dump_lrc(lyrics)
        # 相接的时间标签应该被省略
        # 注意：代码中只省略了与前一词结束时间相等的前缀标签
        # 但后缀标签（end）仍然会输出
        # 第一个词：start=1000(省略) end=1100(输出)
        # 第二个词：start=1100(省略，因为前一个end=1100) end=1200(输出)
        # 第三个词：start=1200(省略，因为前一个end=1200) end=1300(输出)
        assert "[00:01.000]第<00:01.100>一<00:01.200>个<00:01.300>" in result
