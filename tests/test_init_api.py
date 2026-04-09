"""测试 __init__.py 提供的公共 API."""

from __future__ import annotations

import lemony_lrc_parser as llp
from lemony_lrc_parser import dumps, loads
from lemony_lrc_parser.models import LyricLine, Lyrics, LyricWord


class TestLoadsFunction:
    """测试 loads 函数."""

    def test_loads_basic(self) -> None:
        """测试基本的 loads 功能."""
        lrc = """[ti: Test]
[00:01.000]Hello World
"""
        lyrics = loads(lrc)
        assert isinstance(lyrics, Lyrics)
        assert lyrics.metadata.get("ti") == "Test"
        assert len(lyrics.lines) == 1
        assert lyrics.lines[0].content[0].content == "Hello World"

    def test_loads_with_fill_implicit_end(self) -> None:
        """测试带 fill_implicit_line_end 参数的 loads."""
        lrc = """[00:01.000]第一行
[00:05.000]第二行
"""
        lyrics = loads(lrc, fill_implicit_line_end=True)
        assert lyrics.lines[0].end == 5000

    def test_loads_equivalent_to_lyrics_loads(self) -> None:
        """测试 loads 等价于 Lyrics.loads."""
        lrc = """[00:01.000]Test
"""
        lyrics1 = loads(lrc)
        lyrics2 = Lyrics.loads(lrc)
        assert lyrics1.dumps() == lyrics2.dumps()


class TestDumpsFunction:
    """测试 dumps 函数."""

    def test_dumps_basic(self) -> None:
        """测试基本的 dumps 功能."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Hello")]),
        ]
        result = dumps(lyrics)
        assert "[00:01.000]Hello" in result

    def test_dumps_with_options(self) -> None:
        """测试带参数的 dumps."""
        lyrics = Lyrics()
        lyrics.metadata = {"ti": "Test"}
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=[LyricWord(content="逐", start=1000, end=1100)],
            ),
        ]
        result = dumps(lyrics, with_metadata=True, use_bracket_for_byword_tag=True)
        assert "[ti: Test]" in result
        # 检查是否使用了方括号
        assert "[00:01.000]逐" in result

    def test_dumps_equivalent_to_lyrics_dumps(self) -> None:
        """测试 dumps 等价于 lyrics.dumps."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Test")]),
        ]
        result1 = dumps(lyrics)
        result2 = lyrics.dumps()
        assert result1 == result2


class TestModuleImports:
    """测试模块级别的导入."""

    def test_all_exports_available(self) -> None:
        """测试所有公共导出都可用."""
        # 数据模型
        assert hasattr(llp, "BasicLyricLine")
        assert hasattr(llp, "LyricLine")
        assert hasattr(llp, "LyricWord")
        assert hasattr(llp, "Lyrics")

        # 异常
        assert hasattr(llp, "InvalidLyricsError")
        assert hasattr(llp, "LyricsParserError")

        # 主 API
        assert hasattr(llp, "loads")
        assert hasattr(llp, "dumps")

        # 低层 API
        assert hasattr(llp, "dump_lrc")
        assert hasattr(llp, "parse_line")
        assert hasattr(llp, "parse_lrc")

        # 时间标签工具
        assert hasattr(llp, "format_timetag")
        assert hasattr(llp, "parse_timetag")

    def test_old_names_removed(self) -> None:
        """测试旧名称已被移除."""
        # 这些名称在旧版本中存在，现在应该被移除
        assert not hasattr(llp, "NullableStartEndModel")
        assert not hasattr(llp, "StartEndModel")
        # parse_file 被重命名为 parse_lrc
        assert not hasattr(llp, "parse_file")
