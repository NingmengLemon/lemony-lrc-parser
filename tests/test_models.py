"""测试 models 模块的数据模型功能."""

from __future__ import annotations

from lemony_lrc_parser.models import LyricLine, Lyrics, LyricWord


class TestLyricsContainer:
    """测试 Lyrics 类的容器协议实现."""

    def test_iteration(self) -> None:
        """测试迭代功能."""
        lyrics = Lyrics()
        line1 = LyricLine(start=1000, content=[LyricWord(content="第一行")])
        line2 = LyricLine(start=2000, content=[LyricWord(content="第二行")])
        lyrics.lines = [line1, line2]

        lines = list(lyrics)
        assert len(lines) == 2
        assert lines[0].content[0].content == "第一行"
        assert lines[1].content[0].content == "第二行"

    def test_length(self) -> None:
        """测试 len() 功能."""
        lyrics = Lyrics()
        assert len(lyrics) == 0

        lyrics.lines.append(LyricLine(start=1000))
        assert len(lyrics) == 1

        lyrics.lines.append(LyricLine(start=2000))
        assert len(lyrics) == 2

    def test_index_access(self) -> None:
        """测试下标访问."""
        lyrics = Lyrics()
        line1 = LyricLine(start=1000, content=[LyricWord(content="第一行")])
        line2 = LyricLine(start=2000, content=[LyricWord(content="第二行")])
        lyrics.lines = [line1, line2]

        assert lyrics[0].content[0].content == "第一行"
        assert lyrics[1].content[0].content == "第二行"

    def test_slice_access(self) -> None:
        """测试切片访问."""
        lyrics = Lyrics()
        lines = [
            LyricLine(start=1000, content=[LyricWord(content="第一行")]),
            LyricLine(start=2000, content=[LyricWord(content="第二行")]),
            LyricLine(start=3000, content=[LyricWord(content="第三行")]),
        ]
        lyrics.lines = lines

        sliced = lyrics[0:2]
        assert len(sliced) == 2
        assert sliced[0].content[0].content == "第一行"
        assert sliced[1].content[0].content == "第二行"


class TestLyricLineText:
    """测试 LyricLine 的 text 属性."""

    def test_text_property(self) -> None:
        """测试 text 属性拼接内容."""
        line = LyricLine(
            start=1000,
            content=[
                LyricWord(content="Hello ", start=1000, end=1500),
                LyricWord(content="World", start=1500, end=2000),
            ],
        )
        assert line.text == "Hello World"

    def test_empty_content(self) -> None:
        """测试空内容的 text 属性."""
        line = LyricLine(start=1000)
        assert line.text == ""


class TestLyricsCombine:
    """测试 Lyrics 的 combine 方法."""

    def test_combine_basic(self) -> None:
        """测试基本的合并功能."""
        main = Lyrics()
        main.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Hello")]),
            LyricLine(start=2000, content=[LyricWord(content="World")]),
        ]
        main.metadata = {"ti": "Main"}

        translation = Lyrics()
        translation.lines = [
            LyricLine(start=1000, content=[LyricWord(content="你好")]),
            LyricLine(start=2000, content=[LyricWord(content="世界")]),
        ]
        translation.metadata = {"ar": "Translator"}

        combined = main.combine(translation)

        assert len(combined.lines) == 2
        assert combined.lines[0].content[0].content == "Hello"
        assert len(combined.lines[0].reference_lines) == 1
        assert combined.lines[0].reference_lines[0][0].content == "你好"
        assert combined.lines[1].content[0].content == "World"
        assert combined.lines[1].reference_lines[0][0].content == "世界"
        # metadata 应该以 main 为准
        assert combined.metadata.get("ti") == "Main"
        assert combined.metadata.get("ar") == "Translator"

    def test_combine_with_missing_lines(self) -> None:
        """测试当 translation 有 main 没有的行时的处理."""
        main = Lyrics()
        main.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Hello")]),
        ]

        translation = Lyrics()
        translation.lines = [
            LyricLine(start=1000, content=[LyricWord(content="你好")]),
            LyricLine(start=3000, content=[LyricWord(content="额外的行")]),
        ]

        # 默认 other_as_refline_only=True, 额外的行应该被丢弃
        combined = main.combine(translation, other_as_refline_only=True)
        assert len(combined.lines) == 1

        # other_as_refline_only=False, 额外的行应该被保留
        combined = main.combine(translation, other_as_refline_only=False)
        assert len(combined.lines) == 2

    def test_combine_preserves_original(self) -> None:
        """测试合并不会修改原始对象."""
        main = Lyrics()
        main.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Hello")]),
        ]
        main.metadata = {"ti": "Original"}

        translation = Lyrics()
        translation.lines = [
            LyricLine(start=1000, content=[LyricWord(content="你好")]),
        ]

        _ = main.combine(translation)

        # 原始对象不应该被修改
        assert len(main.lines) == 1
        assert len(main.lines[0].reference_lines) == 0
        assert main.metadata.get("ti") == "Original"

    def test_combine_skip_none_start(self) -> None:
        """测试跳过 start 为 None 的行."""
        main = Lyrics()
        main.lines = [
            LyricLine(start=None, content=[LyricWord(content="No start")]),
            LyricLine(start=1000, content=[LyricWord(content="Has start")]),
        ]

        translation = Lyrics()
        translation.lines = [
            LyricLine(start=1000, content=[LyricWord(content="翻译")]),
        ]

        combined = main.combine(translation)
        assert len(combined.lines) == 1
        assert combined.lines[0].content[0].content == "Has start"


class TestLyricsAdd:
    """测试 Lyrics 的 __add__ 方法."""

    def test_add_operator(self) -> None:
        """测试 + 运算符."""
        main = Lyrics()
        main.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Hello")]),
        ]

        translation = Lyrics()
        translation.lines = [
            LyricLine(start=1000, content=[LyricWord(content="你好")]),
        ]

        combined = main + translation

        assert len(combined.lines) == 1
        assert combined.lines[0].content[0].content == "Hello"
        assert len(combined.lines[0].reference_lines) == 1

    def test_add_with_non_lyrics(self) -> None:
        """测试与非 Lyrics 对象相加应该返回 NotImplemented."""
        lyrics = Lyrics()
        result = lyrics.__add__("not lyrics")  # type: ignore
        assert result is NotImplemented


class TestLyricsStr:
    """测试 Lyrics 的 __str__ 方法."""

    def test_str_calls_dumps(self) -> None:
        """测试 __str__ 会调用 dumps."""
        lyrics = Lyrics()
        lyrics.lines = [
            LyricLine(start=1000, content=[LyricWord(content="Hello")]),
        ]

        str_result = str(lyrics)
        dumps_result = lyrics.dumps()
        assert str_result == dumps_result
        assert "[00:01.000]" in str_result
        assert "Hello" in str_result
