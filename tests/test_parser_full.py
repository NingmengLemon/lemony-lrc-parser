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
        assert len(lyrics) == 2
        assert lyrics[0].content[0].content == "主歌词"
        assert len(lyrics[0].reference_lines) == 1
        assert lyrics[0].reference_lines[0][0].content == "翻译行1"

    def test_reference_line_reset(self) -> None:
        """测试空行重置参考行锚点."""
        lrc = """[00:01.000]主歌词1
翻译1

[00:02.000]主歌词2
翻译2
"""
        lyrics = parse_lrc(lrc)
        # 空行应该重置 last_tag, 所以翻译2 应该挂到 主歌词2 上
        assert len(lyrics) == 2
        assert lyrics[1].reference_lines[0][0].content == "翻译2"

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
        assert len(lyrics) == 1

    def test_multiple_time_tags_same_line(self) -> None:
        """测试同一行有多个时间标签."""
        lrc = """[00:01.000][00:05.000]重复歌词
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics) == 2
        assert lyrics[0].content[0].content == "重复歌词"
        assert lyrics[1].content[0].content == "重复歌词"
        assert lyrics[0].start == 1000
        assert lyrics[1].start == 5000

    def test_ambiguous_leading_tags_with_inline_tags_as_single_line(self) -> None:
        """行首连续标签 + 内联标签应按空词元解析为单行, 不展开."""
        lrc = """[00:00.01][00:00.02]歌[00:00.03]词[00:00.04]
"""
        lyrics = parse_lrc(lrc)

        assert len(lyrics) == 1
        line = lyrics[0]
        assert line.start == 10
        assert line.end == 40
        assert [(token.content, token.start, token.end) for token in line.content] == [
            ("", 10, 20),
            ("歌", 20, 30),
            ("词", 30, 40),
        ]

    def test_duplicate_time_tag_as_reference(self) -> None:
        """测试同一时间点的行变为参考行."""
        lrc = """[00:01.000]第一版本
[00:01.000]第二版本
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics) == 1
        assert lyrics[0].content[0].content == "第一版本"
        assert len(lyrics[0].reference_lines) == 1
        assert lyrics[0].reference_lines[0][0].content == "第二版本"


class TestParseLrcFillImplicitEnd:
    """测试 fill_implicit_line_end 功能."""

    def test_fill_implicit_end(self) -> None:
        """测试填充隐式行尾时间."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = """[00:01.000]第一行
[00:05.000]第二行
[00:10.000]第三行
"""
        lyrics = parse_lrc(lrc, options=ParseOptions(fill_implicit_line_end=True))
        assert lyrics[0].end == 5000  # 下一行的开始
        assert lyrics[1].end == 10000  # 下一行的开始
        assert lyrics[2].end is None  # 最后一行没有下一行

    def test_no_fill_implicit_end(self) -> None:
        """测试不填充隐式行尾时间."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = """[00:01.000]第一行
[00:05.000]第二行
"""
        lyrics = parse_lrc(lrc, options=ParseOptions(fill_implicit_line_end=False))
        assert lyrics[0].end is None
        assert lyrics[1].end is None


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
        assert len(lyrics) == 3
        assert lyrics[1].content[0].content == ""
        assert lyrics[1].start == 5000


class TestParseLrcWordLevel:
    """测试逐字歌词解析."""

    def test_byword_line(self) -> None:
        """测试逐字歌词行."""
        lrc = """[00:01.000]<00:01.000>第<00:01.500>一<00:02.000>行[00:03.000]
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics) == 1
        line = lyrics[0]
        assert len(line.content) == 3
        assert line.content[0].content == "第"
        assert line.content[0].start == 1000
        assert line.content[0].end == 1500
        assert line.content[1].content == "一"
        assert line.content[1].start == 1500
        assert line.content[1].end == 2000
        assert line.content[2].content == "行"
        assert line.content[2].start == 2000
        assert line.content[2].end == 3000
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


class TestParseLrcWordTagOnlyLine:
    """测试 B1: 仅含逐字标签 (尖括号) 的行应被解析为歌词行而非参考行."""

    def test_word_tag_only_line_as_lyric(self) -> None:
        """行首为尖括号逐字标签时, 以第一个词元 start 作为 line.start."""
        lrc = """<00:01.000>hello<00:02.000>world<00:03.000>
"""
        lyrics = parse_lrc(lrc)
        # 应该有一个行, start 来自第一个 word tag = 1000ms
        assert len(lyrics) == 1
        line = lyrics[0]
        assert line.start == 1000
        assert len(line.content) == 2
        assert line.content[0].content == "hello"
        assert line.content[0].start == 1000
        assert line.content[0].end == 2000
        assert line.content[1].content == "world"
        assert line.content[1].start == 2000
        assert line.content[1].end == 3000

    def test_word_tag_only_line_after_normal_line(self) -> None:
        """逐字行跟在正常行后面, 不应成为参考行."""
        lrc = """[00:01.000]first
<00:02.000>second<00:03.000>line<00:04.000>
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics) == 2
        assert lyrics[0].text == "first"
        assert lyrics[1].text == "secondline"
        assert lyrics[1].start == 2000
        # 不应有额外参考行
        assert len(lyrics[0].reference_lines) == 0


class TestParseLrcSorting:
    """测试歌词行排序."""

    def test_lines_sorted_by_time(self) -> None:
        """测试歌词行按时间排序."""
        lrc = """[00:05.000]第二行
[00:01.000]第一行
[00:03.000]第三行
"""
        lyrics = parse_lrc(lrc)
        assert len(lyrics) == 3
        assert lyrics[0].start == 1000
        assert lyrics[1].start == 3000
        assert lyrics[2].start == 5000


class TestParseLrcLineFilter:
    """测试 line_filter 黑名单过滤功能."""

    @staticmethod
    def _parse(lrc: str, line_filter):
        from lemony_lrc_parser.models import ParseOptions

        return parse_lrc(lrc, options=ParseOptions(line_filter=line_filter))

    # ── string filter (统一按正则理解, str 会被 compile) ─────────

    def test_string_filter_plain_text(self) -> None:
        """字符串过滤: 普通字符串按正则 search, 命中的行被丢弃."""
        lrc = """[00:01.000]A line to keep
[00:02.000]skip this one
[00:03.000]B line to keep
"""
        lyrics = self._parse(lrc, "skip")
        assert len(lyrics) == 2
        assert "A line" in lyrics[0].text
        assert "B line" in lyrics[1].text

    def test_string_filter_no_match(self) -> None:
        """字符串过滤: 无匹配时不过滤任何行."""
        lrc = """[00:01.000]hello
[00:02.000]world
"""
        lyrics = self._parse(lrc, "zzz")
        assert len(lyrics) == 2

    def test_string_filter_search_semantics(self) -> None:
        """字符串过滤: search 语义, 命中行内任意位置即丢弃."""
        lrc = """[00:01.000]exact
[00:02.000]not exact match
"""
        lyrics = self._parse(lrc, "exact")
        # "exact" 出现在两行文本中的任意位置, 两行都会被过滤
        assert len(lyrics) == 0

    def test_string_filter_compiled_as_regex(self) -> None:
        """字符串过滤: 字符串会被当作正则编译, 元字符按正则解释."""
        lrc = """[00:01.000]abc
[00:02.000]a.c
[00:03.000]xyz
"""
        # "a.c" 作为正则会同时命中 "abc" 与 "a.c", 但不命中 "xyz"
        lyrics = self._parse(lrc, "a.c")
        assert len(lyrics) == 1
        assert lyrics[0].text == "xyz"

    def test_string_filter_with_multiple_time_tags(self) -> None:
        """字符串过滤 + 重复时间标签: 同内容的所有时间点都被过滤."""
        lrc = """[00:01.000]keep
[00:02.000][00:05.000]drop me
[00:10.000]keep too
"""
        lyrics = self._parse(lrc, "drop")
        assert len(lyrics) == 2
        assert lyrics[0].start == 1000
        assert lyrics[1].start == 10000

    # ── regex filter ───────────────────────────────────────────

    def test_regex_filter_basic(self) -> None:
        """正则过滤: 基础模式匹配."""
        lrc = """[00:01.000]abc123
[00:02.000]def456
[00:03.000]ghi789
"""
        import re

        lyrics = self._parse(lrc, re.compile(r"\d+"))
        # 三行都包含数字
        assert len(lyrics) == 0

    def test_regex_filter_selective(self) -> None:
        """正则过滤: 只过滤匹配特定模式的行."""
        lrc = """[00:01.000]keep
[00:02.000]drop-001
[00:03.000]drop-002
[00:04.000]keep too
"""
        import re

        lyrics = self._parse(lrc, re.compile(r"^drop-"))
        assert len(lyrics) == 2
        assert lyrics[0].text == "keep"
        assert lyrics[1].text == "keep too"

    def test_regex_filter_case_insensitive(self) -> None:
        """正则过滤: 大小写不敏感."""
        lrc = """[00:01.000]Hello
[00:02.000]HELLO
[00:03.000]world
"""
        import re

        lyrics = self._parse(lrc, re.compile(r"hello", re.IGNORECASE))
        assert len(lyrics) == 1
        assert lyrics[0].text == "world"

    # ── interaction with other features ────────────────────────

    def test_filter_before_fill_implicit_end(self) -> None:
        """过滤先于 fill_implicit_line_end: 被丢弃的行不影响隐式填充."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = """[00:01.000]keep
[00:05.000]drop
[00:10.000]keep too
"""
        lyrics = parse_lrc(
            lrc,
            options=ParseOptions(line_filter="drop", fill_implicit_line_end=True),
        )
        assert len(lyrics) == 2
        # 过滤后 "keep" 和 "keep too" 相邻, keep 的 end 应为 keep too 的 start
        assert lyrics[0].end == 10000
        assert lyrics[1].end is None  # 最后一行

    def test_filter_preserves_metadata(self) -> None:
        """过滤不影响 metadata 解析."""
        lrc = """[ti:Song]
[00:01.000]keep
[00:02.000]drop
"""
        lyrics = self._parse(lrc, "drop")
        assert lyrics.metadata["ti"] == "Song"
        assert len(lyrics) == 1

    def test_filter_only_main_content_not_reference(self) -> None:
        """过滤只检查主行文本, 参考行不参与匹配."""
        lrc = """[00:01.000]main A
drop ref A
[00:02.000]main B
drop ref B
"""
        lyrics = self._parse(lrc, "drop")
        # 两行主文本都包含 "main" 不包含 "drop", 不会被过滤
        assert len(lyrics) == 2
        # 参考行仍然存在
        assert len(lyrics[0].reference_lines) == 1
        assert lyrics[0].reference_lines[0].text == "drop ref A"

    def test_filter_main_line_matching_removes_refs_too(self) -> None:
        """主行被过滤后, 其参考行也一起消失."""
        lrc = """[00:01.000]main A
ref for A
[00:02.000]main drop me
ref for drop
[00:03.000]main B
ref for B
"""
        lyrics = self._parse(lrc, "drop")
        assert len(lyrics) == 2
        assert lyrics[0].text == "main A"
        assert lyrics[1].text == "main B"

    def test_filter_empty_placeholder_line(self) -> None:
        """空占位行: 空字符串是否被匹配取决于 filter 值."""
        lrc = """[00:01.000]real
[00:05.000]
[00:10.000]another
"""
        # 用非空 filter → 空行不应被过滤
        lyrics = self._parse(lrc, "drop")
        assert len(lyrics) == 3  # 空行保留

    def test_filter_none_noop(self) -> None:
        """line_filter=None 时行为与不传选项一致."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = """[00:01.000]line one
[00:02.000]line two
"""
        lyrics1 = parse_lrc(lrc)
        lyrics2 = parse_lrc(lrc, options=ParseOptions(line_filter=None))
        assert len(lyrics1) == len(lyrics2) == 2
        assert lyrics1[0].text == lyrics2[0].text
