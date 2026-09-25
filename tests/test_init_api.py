"""测试 __init__.py 提供的公共 API."""

from __future__ import annotations

from io import StringIO

import lemony_lrc_parser as llp
from lemony_lrc_parser import dump, dumps, load, loads
from lemony_lrc_parser.models import BasicLyricLine, LyricLine, Lyrics, LyricToken


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
        assert len(lyrics) == 1
        assert lyrics[0].content[0].content == "Hello World"

    def test_loads_with_fill_implicit_end(self) -> None:
        """测试带 fill_implicit_line_end 参数的 loads."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = """[00:01.000]第一行
[00:05.000]第二行
"""
        lyrics = loads(lrc, options=ParseOptions(fill_implicit_line_end=True))
        assert lyrics[0].end == 5000

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
        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000, content=BasicLyricLine([LyricToken(content="Hello")])
                ),
            ]
        )
        result = dumps(lyrics)
        assert "[00:01.000]Hello" in result

    def test_dumps_with_options(self) -> None:
        """测试带参数的 dumps."""
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000,
                    content=BasicLyricLine(
                        [LyricToken(content="逐", start=1000, end=1100)]
                    ),
                ),
            ]
        )
        lyrics.metadata = {"ti": "Test"}
        result = dumps(
            lyrics,
            options=SerializationOptions(
                with_metadata=True, use_bracket_for_byword_tag=True
            ),
        )
        assert "[ti: Test]" in result
        # 检查是否使用了方括号
        assert "[00:01.000]逐" in result

    def test_dumps_equivalent_to_lyrics_dumps(self) -> None:
        """测试 dumps 等价于 lyrics.dumps."""
        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000, content=BasicLyricLine([LyricToken(content="Test")])
                ),
            ]
        )
        result1 = dumps(lyrics)
        result2 = lyrics.dumps()
        assert result1 == result2


class TestLoadFunction:
    """测试 load 函数 (文件 I/O)."""

    def test_load_basic(self) -> None:
        """测试基本的 load 功能."""
        lrc = """[ti: Test]
[00:01.000]Hello World
"""
        with StringIO(lrc) as fp:
            lyrics = load(fp)
        assert isinstance(lyrics, Lyrics)
        assert lyrics.metadata.get("ti") == "Test"
        assert len(lyrics) == 1
        assert lyrics[0].content[0].content == "Hello World"

    def test_load_with_fill_implicit_end(self) -> None:
        """测试带 fill_implicit_line_end 参数的 load."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = """[00:01.000]第一行
[00:05.000]第二行
"""
        with StringIO(lrc) as fp:
            lyrics = load(fp, options=ParseOptions(fill_implicit_line_end=True))
        assert lyrics[0].end == 5000

    def test_load_equivalent_to_lyrics_load(self) -> None:
        """测试 load 等价于 Lyrics.load."""
        lrc = """[00:01.000]Test
"""
        with StringIO(lrc) as fp:
            lyrics1 = load(fp)
        with StringIO(lrc) as fp:
            lyrics2 = Lyrics.load(fp)
        assert lyrics1.dumps() == lyrics2.dumps()


class TestDumpFunction:
    """测试 dump 函数 (文件 I/O)."""

    def test_dump_basic(self) -> None:
        """测试基本的 dump 功能."""
        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000, content=BasicLyricLine([LyricToken(content="Hello")])
                ),
            ]
        )
        with StringIO() as fp:
            dump(lyrics, fp)
            result = fp.getvalue()
        assert "[00:01.000]Hello" in result

    def test_dump_with_options(self) -> None:
        """测试带参数的 dump."""
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000,
                    content=BasicLyricLine(
                        [LyricToken(content="逐", start=1000, end=1100)]
                    ),
                ),
            ]
        )
        lyrics.metadata = {"ti": "Test"}
        with StringIO() as fp:
            dump(
                lyrics,
                fp,
                options=SerializationOptions(
                    with_metadata=True, use_bracket_for_byword_tag=True
                ),
            )
            result = fp.getvalue()
        assert "[ti: Test]" in result
        assert "[00:01.000]逐" in result

    def test_dump_equivalent_to_lyrics_dump(self) -> None:
        """测试 dump 等价于 lyrics.dump."""
        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000, content=BasicLyricLine([LyricToken(content="Test")])
                ),
            ]
        )
        with StringIO() as fp:
            dump(lyrics, fp)
            result1 = fp.getvalue()
        with StringIO() as fp:
            lyrics.dump(fp)
            result2 = fp.getvalue()
        assert result1 == result2

    def test_roundtrip(self) -> None:
        """测试 load → dump → load 往返一致性."""
        lrc = """[ti: Roundtrip]
[ar: TestArtist]
[00:01.000]Hello World
[00:05.000]Goodbye World
"""
        with StringIO(lrc) as fp:
            lyrics = load(fp)
        with StringIO() as fp:
            dump(lyrics, fp)
            dumped = fp.getvalue()
        with StringIO(dumped) as fp:
            lyrics2 = load(fp)

        assert len(lyrics2) == 2
        assert lyrics2.metadata.get("ti") == "Roundtrip"
        assert lyrics2.metadata.get("ar") == "TestArtist"
        assert lyrics2[0].text == "Hello World"
        assert lyrics2[1].text == "Goodbye World"
        assert lyrics2[0].start == 1000
        assert lyrics2[1].start == 5000


class TestModuleImports:
    """测试模块级别的导入."""

    def test_all_exports_available(self) -> None:
        """测试所有公共导出都可用."""
        # 数据模型
        assert hasattr(llp, "BasicLyricLine")
        assert hasattr(llp, "LyricLine")
        assert hasattr(llp, "LyricToken")
        assert hasattr(llp, "Lyrics")

        # 异常
        assert hasattr(llp, "InvalidLyricsError")
        assert hasattr(llp, "LyricsParserError")

        # 主 API
        assert hasattr(llp, "loads")
        assert hasattr(llp, "dumps")
        assert hasattr(llp, "load")
        assert hasattr(llp, "dump")

        # 低层 API
        assert hasattr(llp, "parse_line")
        assert hasattr(llp, "parse_lrc")
        # dump_lrc 已移至 serializer 子模块, 不再从包顶层导出

        # 时间标签工具
        assert hasattr(llp, "format_timetag")
        assert hasattr(llp, "parse_timetag")

        # 验证子系统
        assert hasattr(llp, "ValidationIssue")
        assert hasattr(llp, "ValidationOptions")
        assert hasattr(llp, "ValidationSeverity")
        assert hasattr(llp, "validate_lyrics")

    def test_old_names_removed(self) -> None:
        """测试旧名称已被移除."""
        # 这些名称在旧版本中存在, 现在应该被移除
        assert not hasattr(llp, "NullableStartEndModel")
        assert not hasattr(llp, "StartEndModel")
        # parse_file 被重命名为 parse_lrc
        assert not hasattr(llp, "parse_file")
        # OffsetSemantics 已被移除
        assert not hasattr(llp, "OffsetSemantics")
