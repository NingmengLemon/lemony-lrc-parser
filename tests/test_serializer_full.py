"""测试 serializer 模块的完整功能."""

from __future__ import annotations

from lemony_lrc_parser.models import BasicLyricLine, LyricLine, Lyrics, LyricToken
from lemony_lrc_parser.serializer import dump_lrc


class TestDumpLrcReferenceLines:
    """测试 reference_lines 的序列化."""

    def test_reference_lines_output(self) -> None:
        """测试参考行在输出中."""
        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=BasicLyricLine([LyricToken(content="Main", start=1000)]),
            reference_lines=[
                BasicLyricLine([LyricToken(content="翻译", start=1000)]),
            ],
        )
        lyrics.lines = [line]

        result = dump_lrc(lyrics)
        assert "[00:01.00]Main" in result
        assert "[00:01.00]翻译" in result

    def test_multiple_reference_lines(self) -> None:
        """测试多个参考行."""
        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=BasicLyricLine([LyricToken(content="Main")]),
            reference_lines=[
                BasicLyricLine([LyricToken(content="翻译1")]),
                BasicLyricLine([LyricToken(content="翻译2")]),
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
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=BasicLyricLine([LyricToken(content="Main")]),
            reference_lines=[
                BasicLyricLine(
                    [
                        LyricToken(content="逐", start=1000, end=1100),
                        LyricToken(content="字", start=1100, end=1200),
                    ]
                ),
            ],
        )
        lyrics.lines = [line]

        result = dump_lrc(
            lyrics,
            options=SerializationOptions(use_bracket_for_byword_tag=False),
        )
        # 参考行也应该使用尖括号 (行首是方括号, 逐字标签是尖括号)
        # word_tag_decimal_length=2 (默认): 100ms → 百分秒 10
        assert "[00:01.00]逐<00:01.10>字<00:01.20>" in result
        assert "<00:01.10>" in result


class TestDumpLrcEmptyLyrics:
    """测试空歌词的序列化."""

    def test_empty_lyrics(self) -> None:
        """测试空歌词对象."""
        lyrics = Lyrics()
        result = dump_lrc(lyrics)
        assert result == ""

    def test_empty_lyrics_with_metadata(self) -> None:
        """测试只有 metadata 的空歌词."""
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics()
        lyrics.metadata = {"ti": "Test", "ar": "Artist"}
        result = dump_lrc(lyrics, options=SerializationOptions(with_metadata=True))
        assert "[ti: Test]" in result
        assert "[ar: Artist]" in result


class TestDumpLrcBywordFormatting:
    """测试逐字标签的格式化."""

    def test_byword_with_brackets(self) -> None:
        """测试使用方括号的逐字标签."""
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=BasicLyricLine(
                    [
                        LyricToken(content="逐", start=1000, end=1100),
                        LyricToken(content="字", start=1100, end=1200),
                    ]
                ),
            ),
        ]

        result = dump_lrc(
            lyrics,
            options=SerializationOptions(use_bracket_for_byword_tag=True),
        )
        # 应该使用方括号
        # word_tag_decimal_length=2 (默认): 100ms → 百分秒 10
        assert "[00:01.00]逐" in result
        assert "[00:01.10]字" in result

    def test_byword_with_angle_brackets(self) -> None:
        """测试使用尖括号的逐字标签."""
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=BasicLyricLine(
                    [
                        LyricToken(content="逐", start=1000, end=1100),
                        LyricToken(content="字", start=1100, end=1200),
                    ]
                ),
            ),
        ]

        result = dump_lrc(
            lyrics,
            options=SerializationOptions(use_bracket_for_byword_tag=False),
        )
        # 行首使用方括号, 逐字标签使用尖括号
        # 第一个词的开始时间等于行开始时间, 所以不输出逐字标签
        # word_tag_decimal_length=2 (默认): 100ms → 百分秒 10
        assert "[00:01.00]逐<00:01.10>字<00:01.20>" in result
        assert "<00:01.10>字" in result

    def test_omit_redundant_start_tag(self) -> None:
        """测试省略与行首重复的开始标签."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=BasicLyricLine(
                    [
                        LyricToken(content="第", start=1000, end=1100),
                        LyricToken(content="一", start=1100, end=1200),
                    ]
                ),
            ),
        ]

        result = dump_lrc(lyrics)
        # 第一个词的开始时间等于行开始时间, 不应该重复输出
        assert result.count("[00:01.00]") == 1  # 只有行首标签

    def test_omit_continuous_tags(self) -> None:
        """测试省略与前一词结束时间相接的标签."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1000,
                content=BasicLyricLine(
                    [
                        LyricToken(content="第", start=1000, end=1100),
                        LyricToken(content="一", start=1100, end=1200),
                        LyricToken(content="个", start=1200, end=1300),
                    ]
                ),
            ),
        ]

        result = dump_lrc(lyrics)
        # 相接的时间标签应该被省略
        # 注意: 代码中只省略了与前一词结束时间相等的前缀标签
        # 但后缀标签 (end) 仍然会输出
        # 第一个词: start=1000(省略) end=1100(输出)
        # 第二个词: start=1100(省略, 因为前一个end=1100) end=1200(输出)
        # 第三个词: start=1200(省略, 因为前一个end=1200) end=1300(输出)
        # word_tag_decimal_length=2 (默认): 100ms → 百分秒 10, 200ms → 20, 300ms → 30
        assert "[00:01.00]第<00:01.10>一<00:01.20>个<00:01.30>" in result


class TestDumpLrcNewOptions:
    """测试 v0.3.0 新增的序列化选项."""

    def test_line_tag_decimal_length_2(self) -> None:
        """line_tag_decimal_length=2 时行标签尾数补齐到 2 位.

        tail_digits<3 时尾数含义为百分秒, 需从毫秒截断转换:
        5ms → 0, 50ms → 5, 500ms → 50.
        """
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=5005,  # 5 毫秒 → 百分秒 0
                end=5050,  # 50 毫秒 → 百分秒 5
                content=BasicLyricLine([LyricToken(content="Test")]),
            ),
        ]
        result = dump_lrc(
            lyrics, options=SerializationOptions(line_tag_decimal_length=2)
        )
        # 5ms → 百分秒=0, 50ms → 百分秒=5
        assert "[00:05.00]" in result
        assert "[00:05.05]" in result

    def test_word_tag_decimal_length_2(self) -> None:
        """word_tag_decimal_length=2 时逐字标签尾数补齐到 2 位.

        tail_digits<3 时尾数含义为百分秒, 需从毫秒截断转换:
        5ms → 0, 55ms → 5, 500ms → 50.
        """
        from lemony_lrc_parser.models import SerializationOptions

        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(
                start=1005,  # 5 毫秒 → 百分秒 0
                content=BasicLyricLine(
                    [
                        LyricToken(content="逐", start=1005, end=1055),
                        LyricToken(content="字", start=1055, end=1500),
                    ]
                ),
            ),
        ]
        result = dump_lrc(
            lyrics, options=SerializationOptions(word_tag_decimal_length=2)
        )
        # 行标签: tail_digits=2 (默认)
        # 5ms → 百分秒 0
        assert "[00:01.00]" in result
        # 逐字标签: tail_digits=2
        # 第一个词 start=1005=5ms → 百分秒 0 (等于行首, 省略)
        # 第一个词 end=1055=55ms → 百分秒 5 → "<00:01.05>"
        # 第二个词 start=1055=55ms → 百分秒 5 (等于前一个end, 省略)
        # 第二个词 end=1500=500ms → 百分秒 50 → "<00:01.50>"
        assert "<00:01.05>" in result
        assert "<00:01.50>" in result
