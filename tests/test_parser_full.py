"""测试 parser 模块的完整功能, 包括未覆盖的分支."""

from __future__ import annotations

import pytest

from lemony_lrc_parser.parser import parse_line, parse_lrc


class TestParseLrcMetadata:
    """测试 parse_lrc 的 metadata 处理."""

    def test_basic_metadata(self) -> None:
        """测试基本的 metadata 解析."""
        lrc = """[ti: Test Song]
[ar: Test Artist]
[al: Test Album]
[offset: 500]
[00:01.000]歌词开始
"""
        lyrics = parse_lrc(lrc)
        assert lyrics.metadata.get("ti") == "Test Song"
        assert lyrics.metadata.get("ar") == "Test Artist"
        assert lyrics.metadata.get("al") == "Test Album"
        assert lyrics.metadata.get("offset") == "500"

    def test_metadata_with_spaces(self) -> None:
        """测试带空格的 metadata."""
        lrc = """[ti:  Title with spaces  ]
[00:01.000]歌词
"""
        lyrics = parse_lrc(lrc)
        # 注意: metadata 的 value 会被 strip() 处理
        assert lyrics.metadata.get("ti") == "Title with spaces"


class TestParseLrcReferenceLines:
    """测试 parse_lrc 的参考行处理."""

    def test_reference_line_basic(self) -> None:
        """测试基本的参考行解析."""
        lrc = """[00:01.000]主歌词
翻译行1
[00:02.000]第二行主歌词
翻译行2
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics.lines) == 2
        assert lyrics.lines[0].content[0].content == "主歌词"
        assert len(lyrics.lines[0].reference_lines) == 1
        assert lyrics.lines[0].reference_lines[0][0].content == "翻译行1"

    def test_reference_line_reset(self) -> None:
        """测试空行重置参考行锚点."""
        lrc = """[00:01.000]主歌词1
翻译1

[00:02.000]主歌词2
翻译2
"""
        lyrics = parse_lrc(lrc)
        # 空行应该重置 last_tag, 所以翻译2 应该挂到 主歌词2 上
        assert len(lyrics.lines) == 2
        assert lyrics.lines[1].reference_lines[0][0].content == "翻译2"

    def test_orphaned_reference_line_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """测试孤儿参考行应该产生警告."""
        lrc = """翻译行 (没有主行) 
[00:01.000]主歌词
"""
        import logging

        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc(lrc)
        assert "Orphaned lyric line" in caplog.text
        assert len(lyrics.lines) == 1

    def test_multiple_time_tags_same_line(self) -> None:
        """测试同一行有多个时间标签."""
        lrc = """[00:01.000][00:05.000]重复歌词
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics.lines) == 2
        assert lyrics.lines[0].content[0].content == "重复歌词"
        assert lyrics.lines[1].content[0].content == "重复歌词"
        assert lyrics.lines[0].start == 1000
        assert lyrics.lines[1].start == 5000

    def test_duplicate_time_tag_as_reference(self) -> None:
        """测试同一时间点的行变为参考行."""
        lrc = """[00:01.000]第一版本
[00:01.000]第二版本
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics.lines) == 1
        assert lyrics.lines[0].content[0].content == "第一版本"
        assert len(lyrics.lines[0].reference_lines) == 1
        assert lyrics.lines[0].reference_lines[0][0].content == "第二版本"


class TestParseLrcFillImplicitEnd:
    """测试 fill_implicit_line_end 功能."""

    def test_fill_implicit_end(self) -> None:
        """测试填充隐式行尾时间."""
        lrc = """[00:01.000]第一行
[00:05.000]第二行
[00:10.000]第三行
"""
        lyrics = parse_lrc(lrc, fill_implicit_line_end=True)
        assert lyrics.lines[0].end == 5000  # 下一行的开始
        assert lyrics.lines[1].end == 10000  # 下一行的开始
        assert lyrics.lines[2].end is None  # 最后一行没有下一行

    def test_no_fill_implicit_end(self) -> None:
        """测试不填充隐式行尾时间."""
        lrc = """[00:01.000]第一行
[00:05.000]第二行
"""
        lyrics = parse_lrc(lrc, fill_implicit_line_end=False)
        assert lyrics.lines[0].end is None
        assert lyrics.lines[1].end is None


class TestParseLrcEmptyLines:
    """测试空行处理."""

    def test_empty_placeholder_line(self) -> None:
        """测试空占位行 (只有时间标签没有内容) ."""
        lrc = """[00:01.000]第一行
[00:05.000]
[00:10.000]第三行
"""
        lyrics = parse_lrc(lrc)
        # 空行应该创建一个内容为空的 LyricLine
        assert len(lyrics.lines) == 3
        assert lyrics.lines[1].content[0].content == ""
        assert lyrics.lines[1].start == 5000


class TestParseLrcWordLevel:
    """测试逐字歌词解析."""

    def test_byword_line(self) -> None:
        """测试逐字歌词行."""
        lrc = """[00:01.000]<00:01.000>第<00:01.500>一<00:02.000>行[00:03.000]
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics.lines) == 1
        line = lyrics.lines[0]
        assert len(line.content) == 3
        assert line.content[0].content == "第"
        assert line.content[0].start == 1000
        assert line.content[0].end == 1500
        assert line.content[1].content == "一"
        assert line.content[1].start == 1500
        assert line.content[1].end == 2000
        assert line.content[2].content == "行"
        assert line.content[2].start == 2000
        # 最后一个 word 的 end 被提升到 line.end
        assert line.content[2].end is None
        assert line.end == 3000


class TestParseLineEdgeCases:
    """测试 parse_line 的边界情况."""

    def test_empty_line(self) -> None:
        """测试空行返回 None."""
        assert parse_line("") is None
        assert parse_line("   ") is None
        assert parse_line("\t\t") is None

    def test_whitespace_only_sequence(self) -> None:
        """测试只有空白字符的行."""
        result = parse_line("[00:01.000]   ")
        assert result is not None
        assert result[0].content == "   "


class TestParseLrcSorting:
    """测试歌词行排序."""

    def test_lines_sorted_by_time(self) -> None:
        """测试歌词行按时间排序."""
        lrc = """[00:05.000]第二行
[00:01.000]第一行
[00:03.000]第三行
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics.lines) == 3
        assert lyrics.lines[0].start == 1000
        assert lyrics.lines[1].start == 3000
        assert lyrics.lines[2].start == 5000
