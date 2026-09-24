"""测试 parser 模块的完整功能, 包括未覆盖的分支."""

from __future__ import annotations

import re

import pytest

from lemony_lrc_parser import BasicLyricLine, Lyrics
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

    def test_single_character_metadata_key(self) -> None:
        """单字符 metadata key 也应被识别."""
        lyrics = parse_lrc("[x: value]\n[00:01.000]歌词\n")
        assert lyrics.metadata == {"x": "value"}

    def test_multiple_metatags_on_one_line(self) -> None:
        """整行均为 metatag 时, 一行内的多个 metatag 都应被提取."""
        lyrics = parse_lrc("[ti: Song] [ar: Artist]\n[00:01.000]x\n")
        assert lyrics.metadata.get("ti") == "Song"
        assert lyrics.metadata.get("ar") == "Artist"

    def test_mid_text_metatag_does_not_swallow_line(self) -> None:
        """正文中间的 [key: value] 不应把整行吞成 metadata (B3)."""
        lrc = "[00:01.000]main\nReturn [to: sender] now\n"
        lyrics = parse_lrc(lrc)
        assert "to" not in lyrics.metadata
        # 该行按普通无标签行处理 → 挂为参考行, 正文得以保留
        assert lyrics[0].reference_lines[0].text == "Return [to: sender] now"

    def test_metatag_with_trailing_text_not_metadata(self) -> None:
        """metatag 之后还有正文时整行按歌词处理, 不再静默吞掉正文."""
        lrc = "[ti: Song] trailing text\n[00:01.000]x\n"
        lyrics = parse_lrc(lrc)
        assert "ti" not in lyrics.metadata

    def test_trailing_lyric_whitespace_is_preserved(self) -> None:
        """解析整份 LRC 时保留正文尾随空格."""
        lyrics = parse_lrc("[00:01.000]  歌词  \n")
        assert lyrics[0].text == "  歌词  "

    def test_metatag_then_junk_then_metatag_is_not_metadata(self) -> None:
        """``[ti: a]extra[ar: b]``: 守卫不得被正则回溯绕过而吞掉 ``extra``.

        此前整行锚定判定里的 ``(?P<value>.*?)`` 会把 ``extra`` 吸进第一个
        value 使整行通过判定, 而随后的 ``finditer`` 提取又给出另一组结果,
        于是"判定通过"与"提取结果"不一致, 中间的正文被静默丢弃.
        """
        lyrics = parse_lrc("[ti: a]extra[ar: b]\n[00:01.000]x\n")
        assert lyrics.metadata == {}
        assert [line.text for line in lyrics] == ["x"]

    def test_metatag_value_with_balanced_brackets_is_metadata(self) -> None:
        """value 里的**配对**方括号按原意保留 (社区真实写法, 见 rmpc#519).

        ``[al: Album [Deluxe]]`` 的意图显然是 value = ``Album [Deluxe]``;
        若按"取第一个 ``]``"收尾 (ffmpeg 的做法) 会截断成 ``Album [Deluxe``.
        """
        lyrics = parse_lrc("[al: Album [Deluxe]]\n[00:01.000]x\n")
        assert lyrics.metadata == {"al": "Album [Deluxe]"}

    def test_metatag_value_with_nested_brackets_is_metadata(self) -> None:
        """嵌套更深的配对也算平衡."""
        lyrics = parse_lrc("[ti: outer [a [b] c] end]\n[00:01.000]x\n")
        assert lyrics.metadata == {"ti": "outer [a [b] c] end"}

    def test_metatag_value_with_unbalanced_brackets_is_not_metadata(self) -> None:
        """方括号不平衡时无法确定边界 → 整行不算 metadata, 也不吞正文."""
        for line in ("[ti: 50% ]off]", "[ti: a [b]"):
            lyrics = parse_lrc(f"{line}\n[00:01.000]x\n")
            assert lyrics.metadata == {}, line
            assert [ln.text for ln in lyrics] == ["x"], line

    def test_metadata_value_may_contain_colon_and_spaces(self) -> None:
        """仍支持 value 含冒号/内部空格 (常见写法)."""
        lyrics = parse_lrc("[ti: Song: Live at 9] [ar: 某人]\n[00:01.000]x\n")
        assert lyrics.metadata == {"ti": "Song: Live at 9", "ar": "某人"}


class TestMetatagScannerEdgeCases:
    """metadata 扫描器 (``_parse_metatag_line``) 的边界: 宽松处宽松, 可疑处不做猜测."""

    @pytest.mark.parametrize(
        "line, expected",
        [
            ("[ti: a]", {"ti": "a"}),
            ("[ ti : a ]", {"ti": "a"}),  # key / ':' 两侧允许空白
            ("[ti:a]", {"ti": "a"}),  # 冒号两侧无空白
            ("[ti:]", {"ti": ""}),  # 空 value
            ("[ti:   ]", {"ti": ""}),
            ("[ti: a] [ar: b]", {"ti": "a", "ar": "b"}),  # 一行多个
            ("[ti: a][ar: b]", {"ti": "a", "ar": "b"}),  # 无空格分隔
            ("[a1: x]", {"a1": "x"}),  # key 允许数字 (非首位)
            ("[ti: a][ti: b]", {"ti": "b"}),  # 重复 key: 后者覆盖
            ("[ti: a]", {"ti": "a"}),
        ],
    )
    def test_accepts(self, line: str, expected: dict[str, str]) -> None:
        lyrics = parse_lrc(f"{line}\n[00:01.000]x\n")
        assert lyrics.metadata == expected

    @pytest.mark.parametrize(
        "line",
        [
            "[ti a]",  # 缺 ':'
            "[ti",  # 未闭合
            "[ti:",  # 有 ':' 但未闭合
            "[1ti: a]",  # key 不以字母开头
            "[: a]",  # 缺 key
            "[]",  # 空标签
            "[ti: a",  # 没有收尾的 ']'
            "[ti: a [b]",  # value 方括号不平衡
            "[ti: a]b",  # 标签之后还有正文
            "x[ti: a]",  # 标签之前有正文
        ],
    )
    def test_rejects(self, line: str) -> None:
        lyrics = parse_lrc(f"{line}\n[00:01.000]x\n")

        assert lyrics.metadata == {}, line
        # 该行既不是 metadata 也不是歌词 (无锚点) → 只留下后面那行
        assert [ln.text for ln in lyrics] == ["x"], line

    def test_bracket_balanced_metadata_roundtrips(self) -> None:
        """配对方括号的 value 写出后能被原样读回."""
        lyrics = Lyrics(metadata={"al": "Album [Deluxe] [Remastered]"})
        text = lyrics.dumps()

        assert "[al: Album [Deluxe] [Remastered]]" in text
        assert Lyrics.loads(text).metadata == {"al": "Album [Deluxe] [Remastered]"}


class TestParseLrcBom:
    """测试带 BOM 的输入 (调用方直接 loads() 未按 utf-8-sig 解码的文本) ."""

    def test_bom_before_lyric_line(self) -> None:
        """BOM 不应导致首行歌词被当作孤儿行丢弃."""
        lyrics = parse_lrc("\ufeff[00:01.000]hello\n")
        assert len(lyrics) == 1
        assert lyrics[0].start == 1000
        assert lyrics[0].text == "hello"

    def test_bom_before_metadata(self) -> None:
        """BOM 不应影响后续 metadata 与歌词行的解析."""
        lyrics = parse_lrc("\ufeff[ti: song]\n[00:01.000]hello\n")
        assert lyrics.metadata == {"ti": "song"}
        assert len(lyrics) == 1
        assert lyrics[0].text == "hello"


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
        assert "orphaned lyric line" in caplog.text
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

    def test_duplicate_tags_on_existing_line_do_not_alias(self) -> None:
        """重复折叠标签命中已存在时间点时, 各参考行槽位必须是独立副本."""
        lrc = "[00:01.000]A\n[00:01.000]B\n[00:01.000][00:01.000]C\n"
        lyrics = parse_lrc(lrc)
        refs = lyrics[0].reference_lines
        assert [r.text for r in refs] == ["B", "C", "C"]
        assert refs[1] is not refs[2]
        refs[1][0].content = "MUTATED"
        assert refs[2].text == "C"


class TestParseLrcOutOfRangeBywordTags:
    """越界逐字标签按 SPL 忽略: 行标签/行尾标签为准, 标记本身丢弃.

    SPL: "逐字标记时间戳需要递增, 如果出现时间戳不在行开始时间和结束时间间
    或者小于之前的时间戳, 那么此逐字标记时间戳会被忽略".
    """

    def test_early_byword_tag_is_ignored_line_tag_wins(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``[00:30.000]<00:10.000>hi``: 行仍在 30s, 早于行首的标记被忽略.

        行标签是文件声明的时间, 逐字标记自相矛盾时以行标签为准 (丢弃标记而不是
        搬动整行); 紧随其后的翻译行照旧挂在它下面, 不会变成孤儿行.
        """
        import logging

        lrc = "[00:30.000]<00:10.000>hi\n翻译行\n"
        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc(lrc)

        assert len(lyrics) == 1
        assert lyrics[0].start == 30000
        assert lyrics[0].text == "hi"
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("hi", None, None)
        ]
        assert [r.text for r in lyrics[0].reference_lines] == ["翻译行"]
        assert "before the line start" in caplog.text
        assert "orphaned lyric line" not in caplog.text

    def test_late_byword_tag_does_not_eat_the_line_end(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``a<23s>b<25s>c[24s]``: 晚于行尾的标记被忽略, 行尾标签保住."""
        import logging

        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc("[00:20.000]a<00:23.000>b<00:25.000>c[00:24.000]\n")

        assert len(lyrics) == 1
        line = lyrics[0]
        assert (line.start, line.end) == (20000, 24000)
        assert [(t.content, t.start, t.end) for t in line.content] == [
            ("a", None, 23000),
            ("bc", 23000, 24000),
        ]
        assert "after the line end" in caplog.text

    def test_no_clamping_of_registered_tags(self) -> None:
        """越界过滤已在 parse_line 完成, 注册阶段不再改标签值."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken
        from lemony_lrc_parser.parser import _register_line_at_tags

        content = BasicLyricLine([LyricToken(content="hi", start=10000)])
        pool: dict[int, LyricLine] = {}

        registered = _register_line_at_tags(pool, content, [30000, 40000])

        assert registered == [30000, 40000]
        assert sorted(pool) == [30000, 40000]

    def test_folded_line_keeps_both_occurrences(self) -> None:
        """折叠标签 + 逐字标签: 出现递减 → 按 SPL 当重复行, 两次都在."""
        lyrics = parse_lrc("[00:20.000][00:30.000]你好[00:23.000]椒盐音乐[00:24.000]\n")
        assert [(line.start, line.text) for line in lyrics] == [
            (20000, "你好椒盐音乐"),
            (30000, "你好椒盐音乐"),
        ]
        # 第一行拿到逐字标记, 第二行的标记早于它的行首 → 被忽略
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("你好", None, 23000),
            ("椒盐音乐", 23000, 24000),
        ]
        assert [(t.content, t.start, t.end) for t in lyrics[1].content] == [
            ("你好椒盐音乐", None, None)
        ]

    def test_delayed_first_word_keeps_single_line(self) -> None:
        """非递减 → 首字延迟的逐字行, 仍是一行 (真实语料的常见形态)."""
        lyrics = parse_lrc("[00:05.650][00:05.730]徘[00:06.130]徊[00:06.450]\n")
        assert len(lyrics) == 1
        line = lyrics[0]
        assert line.start == 5650
        assert [(t.content, t.start, t.end) for t in line.content] == [
            ("", 5650, 5730),
            ("徘", 5730, 6130),
            ("徊", 6130, 6450),
        ]

    def test_multi_leading_tags_with_inline_tag_registers_anchor(self) -> None:
        """2a 分支的折叠路径: 每个行首标签都注册, 锚点指向第一个."""
        lrc = "[00:05.000][00:30.000]<00:10.000>hi\n翻译行\n"
        lyrics = parse_lrc(lrc)
        assert [(line.start, line.text) for line in lyrics] == [
            (5000, "hi"),
            (30000, "hi"),
        ]
        assert lyrics[0].reference_lines == []
        # 翻译行挂在最后注册的那一行下面
        assert lyrics[1].reference_lines[0].text == "翻译行"


class TestParseLrcLenientTimeTags:
    """测试宽松时间标签解析 (秒数越界不报错, 但产生 warning) ."""

    def test_out_of_range_seconds_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """秒数 >= 60 的时间标签按字面值折算, 并产生 warning 日志."""
        import logging

        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc("[00:99.000]x\n")
        assert lyrics[0].start == 99000
        assert "seconds >= 60" in caplog.text

    def test_normal_seconds_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """正常秒数不产生 warning."""
        import logging

        with caplog.at_level(logging.WARNING):
            parse_lrc("[00:59.000]x\n")
        assert "seconds >= 60" not in caplog.text


class TestAdjacentEqualTimeTags:
    """相邻时间标签"相等"与"递减"的诊断级别不同.

    真实语料 (6536 份 .lrc) 里相邻相等出现 1917 次 (逐字行中空格词元与下一个
    词共享时间戳), 递减 0 次 —— 前者是正常写法, 不该按 warning 打扰用户.
    """

    def test_equal_adjacent_tag_is_merged_silently(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """相邻的相等标签合并后语义不变, 且不产生 warning.

        语料里的形态是 ``[00:13.205] [00:13.205]via`` (空格词元与下一个词共享
        时间戳), 行首标签已由 ``_split_leading_line_timetags`` 剥掉, 这里模拟的
        是行中间出现的相等标签.
        """
        import logging

        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc("[00:01.000]a[00:02.000] [00:02.000]b\n")

        assert lyrics[0].text == "a b"
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("a", None, 2000),
            (" b", 2000, None),
        ]
        assert "Unordered time tag dropped" not in caplog.text

    def test_decreasing_adjacent_tag_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """真正乱序 (递减) 仍然告警."""
        import logging

        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc("[00:01.000]a[00:02.000]b[00:01.500]c\n")

        assert lyrics[0].text == "abc"
        assert "Unordered time tag dropped" in caplog.text


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
    """空正文行 = SPL 的纯结束标记, 不再产生空歌词行."""

    def test_empty_line_closes_the_previous_line(self) -> None:
        """``[00:05.000]`` 给上一行补 end, 自己不出现在 Lyrics 里."""
        lrc = """[00:01.000]第一行
[00:05.000]
[00:10.000]第三行
"""
        lyrics = parse_lrc(lrc)
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (1000, 5000, "第一行"),
            (10000, None, "第三行"),
        ]

    def test_empty_line_sharing_timestamp_with_next_line(self) -> None:
        """SPL 明说结束标记常与下一句同时间戳: 下一句必须是独立歌词行.

        曾经这里会造一条空占位行, 于是同时间戳的真实歌词被挂成它的参考行
        (翻译), 按 ``line.text`` 遍历的消费者整行丢失.
        """
        lrc = """[00:17.230]main
[00:20.820]
[00:20.820]フィクション
[00:20.820]
[00:20.820]喜欢虚构的
"""
        lyrics = parse_lrc(lrc)
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (17230, 20820, "main"),
            (20820, None, "フィクション"),
        ]
        assert [r.text for r in lyrics[1].reference_lines] == ["喜欢虚构的"]

    def test_leading_empty_line_has_no_target_and_is_dropped(self) -> None:
        """文件首行的空标记没有可收尾的上一行 → 直接忽略."""
        lyrics = parse_lrc("[00:00.000]\n[00:01.000]hello\n")
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (1000, None, "hello")
        ]

    def test_inline_line_end_wins_over_end_marker(self) -> None:
        """同行内的行尾标签优先于后面孤立的结束标记."""
        lyrics = parse_lrc("[00:10.000]a[00:15.000]\n[00:20.000]\n")
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (10000, 15000, "a")
        ]

    def test_end_marker_keeps_fill_implicit_end_from_winning(self) -> None:
        """结束标记写下的 end 不会被 fill_implicit_line_end 覆盖."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = "[00:01.000]a\n[00:05.000]\n[00:10.000]b\n"
        lyrics = parse_lrc(lrc, options=ParseOptions(fill_implicit_line_end=True))
        assert [(line.start, line.end) for line in lyrics] == [
            (1000, 5000),
            (10000, None),
        ]

    def test_whitespace_only_body_is_still_content(self) -> None:
        """标签之后只剩空白仍算正文 (A5a), 不是结束标记."""
        lyrics = parse_lrc("[00:01.000]a\n[00:05.000]  \n")
        assert [(line.start, line.text) for line in lyrics] == [
            (1000, "a"),
            (5000, "  "),
        ]


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
    def _parse(lrc: str, line_filter: str | re.Pattern[str] | None) -> Lyrics:
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

    def test_filter_empty_line_is_an_end_marker_not_a_line(self) -> None:
        """空正文行不再产生歌词行, 因此也不参与 line_filter 的匹配."""
        lrc = """[00:01.000]real
[00:05.000]
[00:10.000]another
"""
        lyrics = self._parse(lrc, "drop")
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (1000, 5000, "real"),
            (10000, None, "another"),
        ]

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

    def test_filter_assigned_after_construction_is_compiled(self) -> None:
        """构造之后再赋值字符串也必须可用 (ParseOptions 是可变 dataclass).

        此前 ``__post_init__`` 是唯一的编译入口, 事后赋值会在解析时以
        ``AttributeError: 'str' object has no attribute 'search'`` 炸掉.
        """
        from lemony_lrc_parser.models import ParseOptions

        options = ParseOptions()
        options.line_filter = "drop me"
        lyrics = parse_lrc("[00:01.000]drop me\n[00:02.000]keep\n", options=options)
        assert [line.text for line in lyrics] == ["keep"]

    def test_filter_reference_line_loses_its_unmatched_text(self) -> None:
        """过滤按主行文本判定: 与主行同时刻的参考行会一起消失 (既有语义)."""
        from lemony_lrc_parser.models import ParseOptions

        lrc = "[00:01.000]drop me\n[00:01.000]keep\n[00:02.000]x\n"
        lyrics = parse_lrc(lrc, options=ParseOptions(line_filter="drop"))
        assert [line.text for line in lyrics] == ["x"]


class TestParseLrcErrorLineInfo:
    """测试 parse_lrc 异常时附带的 line_no / raw_line 信息."""

    def test_invalid_lyrics_gets_line_no(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """parse_lrc 抛出的 InvalidLyricsError 应自动附加 line_no 和 raw_line."""
        # 通过 monkeypatch parse_line 来触发 InvalidLyricsError,
        # 测试 parse_lrc 中新加的 try/except 包装逻辑
        import lemony_lrc_parser.parser as parser_mod
        from lemony_lrc_parser.exceptions import InvalidLyricsError

        def _fail_parse_line(line: str, **kwargs: object) -> None:
            raise InvalidLyricsError("simulated failure")

        monkeypatch.setattr(parser_mod, "parse_line", _fail_parse_line)
        lrc = "[00:01.000]some line\n"
        with pytest.raises(InvalidLyricsError) as exc_info:
            parse_lrc(lrc)
        err = exc_info.value
        assert err.line_no is not None, "line_no should be populated"
        assert err.raw_line is not None, "raw_line should be populated"
        assert err.line_no >= 1
        assert isinstance(err.raw_line, str)

    def test_ambiguous_leading_tags_error_has_line_info(self) -> None:
        """多行首标签 + 含时间标签的正交 且无法产生 line start 时,
        错误应带 line_no / raw_line."""
        # 场景: 多个行首 [time] 标签, 剩余正文还含有时间标签 (标签非递减,
        # 因此走"首字延迟"的单行读法), 但 parse_line 返回的 line.start 为 None
        import lemony_lrc_parser.parser as parser_mod
        from lemony_lrc_parser.exceptions import InvalidLyricsError

        orig = parser_mod.parse_line

        def _bad_parse_line(line: str, **kwargs: object) -> BasicLyricLine | None:
            from lemony_lrc_parser.models import BasicLyricLine, LyricToken

            return BasicLyricLine([LyricToken(content="x", start=None, end=None)])

        try:
            # ty 认为模块属性不可重新赋值, 这里的 monkeypatch 是刻意的
            parser_mod.parse_line = _bad_parse_line  # ty: ignore[invalid-assignment]
            lrc = "[00:01.000][00:01.500]text <00:02.000>extra"
            with pytest.raises(InvalidLyricsError) as exc_info:
                parse_lrc(lrc)
            err = exc_info.value
            assert err.line_no is not None
            assert err.raw_line is not None
        finally:
            parser_mod.parse_line = orig

    def test_orphaned_line_warning_has_line_no(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """孤立行 (无锚点且无时间标签) 的 warning 日志应包含行号."""
        import logging

        # 先有空行重置 last_tag, 再出现无时间标签的文本行
        lrc = "[00:01.000]anchor\n\norphan text"
        with caplog.at_level(logging.WARNING):
            parse_lrc(lrc)
        assert "orphaned lyric line" in caplog.text
        # 新格式包含 "Line N:" 前缀
        assert "Line 3:" in caplog.text
