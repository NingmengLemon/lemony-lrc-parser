"""测试 models 模块的数据模型功能."""

from __future__ import annotations

import re
import warnings

import pytest

from lemony_lrc_parser import COMMON_METADATA_KEYS, MetadataDict, MetadataKey
from lemony_lrc_parser.models import BasicLyricLine, LyricLine, Lyrics, LyricToken
from lemony_lrc_parser.regex import METATAG_KEY_REGEX, compile_regex


def _line(start: int, text: str) -> LyricLine:
    return LyricLine(start=start, content=BasicLyricLine([LyricToken(content=text)]))


class TestLyricsContainer:
    """测试 Lyrics 类的容器协议实现 (直接继承 UserList)."""

    def test_iteration(self) -> None:
        """测试迭代功能."""
        lyrics = Lyrics([_line(1000, "第一行"), _line(2000, "第二行")])

        lines = list(lyrics)
        assert len(lines) == 2
        assert lines[0].content[0].content == "第一行"
        assert lines[1].content[0].content == "第二行"

    def test_length(self) -> None:
        """测试 len() 功能."""
        lyrics = Lyrics()
        assert len(lyrics) == 0

        lyrics.append(LyricLine(start=1000))
        assert len(lyrics) == 1

        lyrics.append(LyricLine(start=2000))
        assert len(lyrics) == 2

    def test_index_access(self) -> None:
        """测试下标访问."""
        lyrics = Lyrics([_line(1000, "第一行"), _line(2000, "第二行")])

        assert lyrics[0].content[0].content == "第一行"
        assert lyrics[1].content[0].content == "第二行"

    def test_slice_access(self) -> None:
        """测试切片访问."""
        lyrics = Lyrics(
            [_line(1000, "第一行"), _line(2000, "第二行"), _line(3000, "第三行")]
        )

        sliced = lyrics[0:2]
        assert len(sliced) == 2
        assert sliced[0].content[0].content == "第一行"
        assert sliced[1].content[0].content == "第二行"

    def test_slice_preserves_independent_metadata(self) -> None:
        """切片保留 metadata, 且 metadata 与原对象独立."""
        lyrics = Lyrics([_line(1000, "第一行")], metadata={"ti": "标题"})
        sliced = lyrics[:]
        assert sliced.metadata == {"ti": "标题"}
        sliced.metadata["ti"] = "修改后"
        assert lyrics.metadata["ti"] == "标题"

    def test_extend_and_append(self) -> None:
        """测试 extend / append 等标准列表操作."""
        lyrics = Lyrics()
        lyrics.extend([_line(1000, "a"), _line(2000, "b")])
        lyrics.append(_line(3000, "c"))
        assert [line.text for line in lyrics] == ["a", "b", "c"]


class TestLyricLineText:
    """测试 LyricLine 的 text 属性."""

    def test_text_property(self) -> None:
        """测试 text 属性拼接内容."""
        line = LyricLine(
            start=1000,
            content=BasicLyricLine(
                [
                    LyricToken(content="Hello ", start=1000, end=1500),
                    LyricToken(content="World", start=1500, end=2000),
                ]
            ),
        )
        assert line.text == "Hello World"

    def test_empty_content(self) -> None:
        """测试空内容的 text 属性."""
        line = LyricLine(start=1000)
        assert line.text == ""

    def test_duration_from_explicit_end(self) -> None:
        assert LyricLine(start=1000, end=3000).duration == 2000

    def test_duration_is_none_without_end(self) -> None:
        """LRC 的行尾时间可选, 所以 None 是常态."""
        assert LyricLine(start=1000).duration is None

    def test_duration_of_parsed_line(self) -> None:
        lyrics = Lyrics.loads("[00:01.000]a[00:03.000]\n[00:05.000]b\n")
        assert [line.duration for line in lyrics] == [2000, None]

    def test_duration_follows_offset(self) -> None:
        """整体偏移把两端一起挪, 时长不变."""
        lyrics = Lyrics.loads("[00:01.000]a[00:03.000]\n")
        assert (lyrics >> 500)[0].duration == lyrics[0].duration == 2000

    def test_duration_of_zero_length_line(self) -> None:
        """手工构造的零长度区间给出 0 (解析器不会产出这种行)."""
        assert LyricLine(start=1000, end=1000).duration == 0

    def test_contains_text_is_the_explicit_api(self) -> None:
        """文本查找走 contains_text(); `in` 的旧语义保留但会告警."""
        content = BasicLyricLine(
            [
                LyricToken(content="Hello ", start=1000, end=1500),
                LyricToken(content="World", start=1500, end=2000),
            ]
        )
        line = LyricLine(start=1000, content=content)

        # 显式方法: 主行文本的子串判定 (跨词元也可以)
        assert line.contains_text("Hello")
        assert line.contains_text("lo Wo")
        assert line.content.contains_text("lo Wo")
        assert not line.contains_text("nope")

        # 旧行为保留: BasicLyricLine 的子串语义, LyricLine 仍是词元相等判定
        # (即 str 恒为 False) —— 两者都会发 DeprecationWarning.
        with pytest.warns(DeprecationWarning, match="BasicLyricLine.contains_text"):
            assert "Hello" in line.content
        with pytest.warns(DeprecationWarning, match="LyricLine.contains_text"):
            assert "Hello" not in line

        # 词元判定在两个模型上都保持"相等"语义, 且不发告警
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert line.content[0] in line
            assert line.content[0] in line.content

        # 显式切片返回的仍是 BasicLyricLine
        assert isinstance(line[0:1], BasicLyricLine)


class TestLyricsCombine:
    """测试 Lyrics 的 combine 方法."""

    def test_combine_basic(self) -> None:
        """测试基本的合并功能."""
        main = Lyrics([_line(1000, "Hello"), _line(2000, "World")])
        main.metadata = {"ti": "Main"}

        translation = Lyrics([_line(1000, "你好"), _line(2000, "世界")])
        translation.metadata = {"ar": "Translator"}

        combined = main.combine(translation)

        assert len(combined) == 2
        assert combined[0].content[0].content == "Hello"
        assert len(combined[0].reference_lines) == 1
        assert combined[0].reference_lines[0][0].content == "你好"
        assert combined[1].content[0].content == "World"
        assert combined[1].reference_lines[0][0].content == "世界"
        # metadata 应该以 main 为准
        assert combined.metadata.get("ti") == "Main"
        assert combined.metadata.get("ar") == "Translator"

    def test_combine_with_missing_lines(self) -> None:
        """测试当 translation 有 main 没有的行时的处理."""
        main = Lyrics([_line(1000, "Hello")])

        translation = Lyrics([_line(1000, "你好"), _line(3000, "额外的行")])

        # 默认 other_as_refline_only=True, 额外的行应该被丢弃
        combined = main.combine(translation, other_as_refline_only=True)
        assert len(combined) == 1

        # other_as_refline_only=False, 额外的行应该被保留
        combined = main.combine(translation, other_as_refline_only=False)
        assert len(combined) == 2

    def test_combine_preserves_original(self) -> None:
        """测试合并不会修改原始对象."""
        main = Lyrics([_line(1000, "Hello")])
        main.metadata = {"ti": "Original"}

        translation = Lyrics([_line(1000, "你好")])

        _ = main.combine(translation)

        # 原始对象不应该被修改
        assert len(main) == 1
        assert len(main[0].reference_lines) == 0
        assert main.metadata.get("ti") == "Original"


class TestLyricsAdd:
    """测试 Lyrics 的 __add__ 方法."""

    def test_add_operator(self) -> None:
        """测试 + 运算符."""
        main = Lyrics([_line(1000, "Hello")])
        translation = Lyrics([_line(1000, "你好")])

        combined = main + translation

        assert len(combined) == 1
        assert combined[0].content[0].content == "Hello"
        assert len(combined[0].reference_lines) == 1

    def test_add_with_non_lyrics(self) -> None:
        """测试与非 Lyrics 对象相加应该返回 NotImplemented."""
        lyrics = Lyrics()
        # 故意传错类型: 运行时会走 isinstance 分支返回 NotImplemented
        result = lyrics.__add__("not lyrics")  # ty: ignore[invalid-argument-type]
        assert result is NotImplemented

    def test_add_keeps_unmatched_lines(self) -> None:
        """+ 运算符不丢弃时间戳对不上的行 (与 combine 默认行为不同) ."""
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(9000, "B")])

        combined = main + other

        assert [line.text for line in combined] == ["A", "B"]
        assert [line.start for line in combined] == [1000, 9000]

    def test_iadd_keeps_unmatched_lines(self) -> None:
        """+= 运算符同样不丢行."""
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(9000, "B")])

        main += other

        assert [line.text for line in main] == ["A", "B"]
        assert [line.start for line in main] == [1000, 9000]


class TestSafeMutation:
    """``add_line`` / ``sort_inplace`` / ``sorted``: 保持时间顺序的安全路径.

    ``Lyrics`` 是 ``UserList``, 直接 ``append`` 不会排序; 而 ``lyrics.sort()`` 又因为
    ``LyricLine`` 不可比较而抛 TypeError —— 这组方法填的就是这个空.
    """

    def test_add_line_keeps_order(self) -> None:
        lyrics = Lyrics(metadata={"ti": "T"})
        for start in (5000, 1000, 3000):
            lyrics.add_line(_line(start, str(start)))

        assert [line.start for line in lyrics] == [1000, 3000, 5000]
        assert lyrics.metadata["ti"] == "T"

    def test_add_line_without_sort_appends(self) -> None:
        lyrics = Lyrics()
        lyrics.add_line(_line(5000, "b"), sort=False)
        lyrics.add_line(_line(1000, "a"), sort=False)

        assert [line.start for line in lyrics] == [5000, 1000]

    def test_add_line_stores_a_reference(self) -> None:
        """与 ``append`` 一致存引用, 不是拷贝 (类文档里写明的语义)."""
        line = _line(1000, "a")
        lyrics = Lyrics()
        lyrics.add_line(line)

        line.start = 2000

        assert lyrics[0].start == 2000

    @pytest.mark.parametrize("bad", ["text", 42, None, ["not a line"]])
    def test_add_line_rejects_non_lines(self, bad: object) -> None:
        with pytest.raises(TypeError, match="expects a LyricLine"):
            Lyrics().add_line(bad)  # ty: ignore[invalid-argument-type]

    def test_plain_list_sort_raises(self) -> None:
        """文档里承诺的那个坑: ``UserList.sort`` 对 LyricLine 不可用."""
        lyrics = Lyrics()
        lyrics.add_line(_line(2000, "b"), sort=False)
        lyrics.add_line(_line(1000, "a"), sort=False)

        with pytest.raises(TypeError):
            lyrics.sort()  # ty: ignore[invalid-argument-type]

    def test_sort_inplace_is_stable(self) -> None:
        """同一时间戳的多行保持原有相对顺序 (对唱 / 重复副歌)."""
        lyrics = Lyrics()
        lyrics.add_line(_line(1000, "first"), sort=False)
        lyrics.add_line(_line(1000, "second"), sort=False)
        lyrics.add_line(_line(500, "earlier"), sort=False)

        lyrics.sort_inplace()

        assert [line.text for line in lyrics] == ["earlier", "first", "second"]

    def test_sort_inplace_keeps_the_same_objects(self) -> None:
        """原地排序不换对象, 只是换位置."""
        first, second = _line(2000, "b"), _line(1000, "a")
        lyrics = Lyrics()
        lyrics.add_line(first, sort=False)
        lyrics.add_line(second, sort=False)

        lyrics.sort_inplace()

        assert lyrics[0] is second
        assert lyrics[1] is first

    def test_sort_inplace_fixes_unsorted(self) -> None:
        lyrics = Lyrics()
        lyrics.add_line(_line(2000, "b"), sort=False)
        lyrics.add_line(_line(1000, "a"), sort=False)
        assert [issue.code for issue in lyrics.validate()] == ["unsorted"]

        lyrics.sort_inplace()

        assert [issue.code for issue in lyrics.validate()] == []

    def test_sorted_returns_an_independent_copy(self) -> None:
        lyrics = Lyrics(metadata={"ti": "T"})
        lyrics.add_line(_line(2000, "b"), sort=False)
        lyrics.add_line(_line(1000, "a"), sort=False)

        ordered = lyrics.sorted()

        assert ordered is not lyrics
        assert [line.start for line in ordered] == [1000, 2000]
        assert [line.start for line in lyrics] == [2000, 1000]  # 原对象没动
        assert ordered.metadata["ti"] == "T"
        # 副本里的行也是拷贝 (与 copy() 一致)
        assert ordered[0] is not lyrics[1]

    def test_sorted_of_sorted_is_equal(self) -> None:
        lyrics = Lyrics()
        lyrics.add_line(_line(1000, "a"))
        lyrics.add_line(_line(2000, "b"))

        assert lyrics.sorted() == lyrics


class TestLyricsStr:
    """测试 Lyrics 的 __str__ 方法."""

    def test_str_calls_dumps(self) -> None:
        """测试 __str__ 会调用 dumps."""
        lyrics = Lyrics([_line(1000, "Hello")])

        str_result = str(lyrics)
        dumps_result = lyrics.dumps()
        assert str_result == dumps_result
        assert "[00:01.000]" in str_result
        assert "Hello" in str_result


class TestCompactRepr:
    """``repr`` 是给调试看的紧凑形式, 与 ``str`` (= dumps) 分工明确."""

    def test_token_repr(self) -> None:
        assert repr(LyricToken("hello", start=1000, end=1500)) == (
            "LyricToken('hello', start=1000, end=1500)"
        )

    def test_token_repr_with_unknown_times(self) -> None:
        assert repr(LyricToken("hello")) == "LyricToken('hello', start=None, end=None)"

    def test_line_repr_hides_tokens(self) -> None:
        """逐字行的词元不铺开 —— 这正是这个 repr 存在的理由."""
        line = Lyrics.loads("[00:00.000]<00:00.249>风<00:00.467>透[00:02.740]\n")[0]
        assert len(line.content) == 2

        text = repr(line)

        assert text == "LyricLine(start=0, end=2740, text='风透')"
        assert "LyricToken" not in text

    def test_line_repr_mentions_reference_lines_only_when_present(self) -> None:
        plain = Lyrics.loads("[00:01.000]a\n")[0]
        assert repr(plain) == "LyricLine(start=1000, end=None, text='a')"

        with_ref = Lyrics.loads("[00:01.000]a\n翻译\n[00:02.000]b\n")[0]
        assert repr(with_ref) == "LyricLine(start=1000, end=None, text='a', refs=1)"

    def test_lyrics_repr_hides_lines(self) -> None:
        lyrics = Lyrics.loads("[ti: A]\n[00:01.000]a\n[00:02.000]b\n")

        text = repr(lyrics)

        assert text == "Lyrics(lines=2, metadata=Metadata({'ti': 'A'}))"
        assert "LyricLine" not in text
        assert "\n" not in text

    def test_lyrics_repr_keeps_duplicate_metadata(self) -> None:
        """metadata 用 Metadata 自己的 repr, 重复项不会被折叠掉."""
        lyrics = Lyrics.loads("[ti: A]\n[ti: B]\n[00:01.000]x\n")
        assert repr(lyrics) == (
            "Lyrics(lines=1, metadata=Metadata([('ti', 'A'), ('ti', 'B')]))"
        )

    def test_empty_lyrics_repr(self) -> None:
        assert repr(Lyrics()) == "Lyrics(lines=0, metadata=Metadata({}))"

    def test_str_still_dumps(self) -> None:
        """紧凑的是 repr; str() 仍然等价于 dumps()."""
        lyrics = Lyrics.loads("[ti: A]\n[00:01.000]a\n")
        assert str(lyrics) == lyrics.dumps()
        assert repr(lyrics) != str(lyrics)

    def test_repr_of_a_real_document_stays_short(self) -> None:
        """逐字 + 翻译的文档, repr 不该把终端刷满."""
        lyrics = Lyrics.loads(
            "[00:01.000]<00:01.100>a<00:01.200>b<00:01.300>c[00:02.000]\n翻译一\n翻译二\n"
        )
        assert len(repr(lyrics)) < 80
        assert len(repr(lyrics[0])) < 80


class TestLyricLineStartValidation:
    """测试 LyricLine.start 的运行时校验."""

    def test_start_none_raises_programming_error(self) -> None:
        """start=None 属于调用方编程错误, 应抛 ProgrammingError."""
        from lemony_lrc_parser.exceptions import ProgrammingError

        with pytest.raises(ProgrammingError):
            LyricLine(start=None)  # ty: ignore[invalid-argument-type]


class TestLyricsCombineDuplicateStarts:
    """self 含重复 start 时合并不得丢行."""

    def test_add_preserves_duplicate_start_lines(self) -> None:
        """+ 运算符保留 self 中同 start 的多行, other 挂到首行.

        此前 ``combine_inplace`` 用 ``dict[start] -> line`` 建池, self 中
        同 start 的后行会覆盖前行, 导致静默丢行.
        """
        main = Lyrics([_line(1000, "A"), _line(1000, "B")])
        other = Lyrics([_line(1000, "你好")])

        combined = main + other

        assert [line.text for line in combined] == ["A", "B"]
        assert [line.start for line in combined] == [1000, 1000]
        assert combined[0].reference_lines[0].text == "你好"
        assert combined[1].reference_lines == []

    def test_combine_preserves_duplicate_start_lines(self) -> None:
        """combine 同样保留 self 中同 start 的多行."""
        main = Lyrics([_line(1000, "A"), _line(1000, "B")])
        other = Lyrics([_line(1000, "你好")])

        combined = main.combine(other)

        assert [line.text for line in combined] == ["A", "B"]
        assert combined[0].reference_lines[0].text == "你好"

    def test_iadd_preserves_duplicate_start_lines(self) -> None:
        """+= 同样保留 self 中同 start 的多行."""
        main = Lyrics([_line(1000, "A"), _line(1000, "B")])
        main += Lyrics([_line(2000, "C")])

        assert [line.text for line in main] == ["A", "B", "C"]

    def test_combine_rejects_single_lyric_line(self) -> None:
        """传入单个 LyricLine 应显式报错, 而不是静默 no-op."""
        lyrics = Lyrics([_line(1000, "a")])

        with pytest.raises(TypeError):
            lyrics.combine(_line(2000, "b"))  # ty: ignore[invalid-argument-type]

    def test_combine_rejects_str(self) -> None:
        """传入字符串应显式报错, 而不是被当成字符序列静默忽略."""
        lyrics = Lyrics([_line(1000, "a")])

        with pytest.raises(TypeError):
            lyrics.combine("not lyrics")  # ty: ignore[invalid-argument-type]

    @pytest.mark.parametrize(
        "other",
        [{"00:01": 1}, b"bytes", iter(["x"]), [1, 2, 3], (None,)],
        ids=["dict", "bytes", "iterator", "int-list", "none-tuple"],
    )
    def test_combine_rejects_iterable_without_lyric_lines(self, other: object) -> None:
        """非空但没有一条 LyricLine 的可迭代对象应报错, 而不是静默 no-op."""
        lyrics = Lyrics([_line(1000, "a")])

        with pytest.raises(TypeError) as exc_info:
            lyrics.combine(other)  # ty: ignore[invalid-argument-type]
        assert "iterable of LyricLine" in str(exc_info.value)

    @pytest.mark.parametrize(
        "other", [[], (), Lyrics()], ids=["list", "tuple", "lyrics"]
    )
    def test_combine_accepts_empty_iterables(self, other: object) -> None:
        """真正的空容器仍然是合法的 no-op."""
        lyrics = Lyrics([_line(1000, "a")])

        combined = lyrics.combine(other)  # ty: ignore[invalid-argument-type]
        assert [line.text for line in combined] == ["a"]

    def test_combine_does_not_mutate_metadata_when_rejecting(self) -> None:
        """入参非法时不应先把 metadata 合并进来 (改一半再报错)."""
        lyrics = Lyrics([_line(1000, "a")])
        lyrics.metadata = {"ti": "Main"}
        other = {"ar": "Whoever"}

        with pytest.raises(TypeError):
            lyrics.combine_inplace(other)  # ty: ignore[invalid-argument-type]
        assert lyrics.metadata == {"ti": "Main"}

    def test_combine_reports_offending_item_types(self) -> None:
        """报错信息里带上有问题的元素类型, 便于定位."""
        lyrics = Lyrics([_line(1000, "a")])

        with pytest.raises(TypeError) as exc_info:
            lyrics.combine([1, "x"])  # ty: ignore[invalid-argument-type]
        assert "int" in str(exc_info.value) and "str" in str(exc_info.value)


class TestTextSearch:
    """``contains_text`` / ``find_text``: 文本查找的显式入口."""

    def _lyrics(self) -> Lyrics:
        line = LyricLine(
            start=1000,
            content=BasicLyricLine(
                [
                    LyricToken(content="Hello ", start=1000, end=1500),
                    LyricToken(content="World", start=1500, end=2000),
                ]
            ),
            reference_lines=[BasicLyricLine([LyricToken(content="你好，世界")])],
        )
        return Lyrics([line, _line(3000, "Bye")])

    def test_lyrics_contains_text_searches_main_and_reference_lines(self) -> None:
        lyrics = self._lyrics()

        assert lyrics.contains_text("Hello")
        assert lyrics.contains_text("lo Wo")  # 跨词元子串
        assert lyrics.contains_text("你好")  # 参考行
        assert lyrics.contains_text("Bye")
        assert not lyrics.contains_text("hello")  # 区分大小写
        assert not lyrics.contains_text("missing")

    def test_find_text_returns_matching_lines(self) -> None:
        lyrics = self._lyrics()

        assert [line.text for line in lyrics.find_text("World")] == ["Hello World"]
        assert [line.text for line in lyrics.find_text("你好")] == ["Hello World"]
        assert lyrics.find_text("missing") == []

    def test_str_in_lyrics_keeps_old_semantics_with_warning(self) -> None:
        """`"xxx" in lyrics` 仍是行相等判定 (恒 False), 但会告警."""
        lyrics = self._lyrics()

        with pytest.warns(DeprecationWarning, match="Lyrics.contains_text"):
            assert "Hello" not in lyrics

    def test_line_in_lyrics_still_works_without_warning(self) -> None:
        """行对象判定不受影响, 也不该打扰用户."""
        lyrics = self._lyrics()

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert lyrics[0] in lyrics
            assert _line(3000, "Bye") in lyrics
            assert _line(9999, "Bye") not in lyrics

    def test_token_contains_text(self) -> None:
        token = LyricToken(content="Hello")

        assert token.contains_text("ell")
        assert not token.contains_text("Helloo")
        with pytest.warns(DeprecationWarning, match="LyricToken.contains_text"):
            assert "ell" in token
        # 非 str 的成员判定保持旧行为: 恒 False, 且不告警
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert 1 not in token


class TestRegexSearch:
    """``find_regex`` / ``contains_regex``: 逐行正则查找."""

    def _lyrics(self) -> Lyrics:
        return Lyrics.loads(
            "[00:01.000]Hello World\n[00:02.000]你好\n翻译 Love\n[00:03.000]no match\n"
        )

    def test_string_pattern_is_compiled(self) -> None:
        assert [line.text for line in self._lyrics().find_regex("o W")] == [
            "Hello World"
        ]

    def test_compiled_pattern(self) -> None:
        lyrics = self._lyrics()
        assert [line.text for line in lyrics.find_regex(re.compile(r"^Hello"))] == [
            "Hello World"
        ]

    def test_reference_lines_included_by_default(self) -> None:
        assert [line.text for line in self._lyrics().find_regex("Love")] == ["你好"]

    def test_reference_lines_can_be_excluded(self) -> None:
        lyrics = self._lyrics()
        assert lyrics.find_regex("Love", include_reference_lines=False) == []

    def test_case_insensitive_via_flags(self) -> None:
        """忽略大小写不是单独的参数, 传 flags 即可 (免得参数越加越多)."""
        lyrics = self._lyrics()
        assert lyrics.find_regex("hello") == []
        assert [line.text for line in lyrics.find_regex(re.compile("hello", re.I))] == [
            "Hello World"
        ]

    def test_escape_makes_it_literal(self) -> None:
        lyrics = self._lyrics()
        assert [line.text for line in lyrics.find_regex(re.escape("o W"))] == [
            "Hello World"
        ]
        # 未转义时 '.' 是元字符, 匹配不到字面量
        assert lyrics.find_regex(re.escape("o.W")) == []

    def test_metacharacters_work(self) -> None:
        assert [line.text for line in self._lyrics().find_regex(r"你.")] == ["你好"]

    def test_no_match(self) -> None:
        lyrics = self._lyrics()
        assert lyrics.find_regex("zzz") == []
        assert not lyrics.contains_regex("zzz")

    def test_matching_is_line_scoped(self) -> None:
        """逐行匹配, 不跨行: pattern 里的 \\n 永远匹配不到."""
        lyrics = Lyrics.loads("[00:01.000]ab\n[00:02.000]cd\n")
        assert lyrics.find_regex("b") != []
        assert lyrics.find_regex(r"b\n") == []
        assert lyrics.find_regex(r"ab[\s\S]*cd") == []

    def test_returns_the_line_objects_themselves(self) -> None:
        lyrics = self._lyrics()
        assert lyrics.find_regex("Hello")[0] is lyrics[0]

    def test_contains_regex_mirrors_find_regex(self) -> None:
        lyrics = self._lyrics()
        assert lyrics.contains_regex("World")
        assert lyrics.contains_regex("Love")  # 参考行
        assert not lyrics.contains_regex("Love", include_reference_lines=False)

    def test_empty_lyrics(self) -> None:
        assert Lyrics().find_regex("anything") == []


class TestMetadataTypingHints:
    """常见 metadata key 的类型提示 (仅提示, 不强制)."""

    def test_common_keys_and_typed_dict_agree(self) -> None:
        assert set(MetadataDict.__annotations__) == set(COMMON_METADATA_KEYS)

    def test_common_keys_are_accepted_by_the_parser_rule(self) -> None:
        """常见 key 必须都能通过解析端的 key 规则, 否则提示会误导人."""
        key_pattern = compile_regex(rf"^{METATAG_KEY_REGEX}$")
        for key in COMMON_METADATA_KEYS:
            assert key_pattern.match(key) is not None, key

    def test_metadata_key_literal_matches_common_keys(self) -> None:
        from typing import get_args

        assert tuple(get_args(MetadataKey)) == COMMON_METADATA_KEYS

    def test_non_standard_keys_are_freely_usable(self) -> None:
        """非标准 key 依旧可以自由使用 (库不做校验)."""
        lyrics = Lyrics.loads("[tool: whatever]\n[00:01.000]x\n")

        assert lyrics.metadata == {"tool": "whatever"}
        assert lyrics.metadata["tool"] == "whatever"


class TestLyricsEquality:
    """两份 ``Lyrics`` 比行序列 + metadata; 与普通列表比只比行."""

    def test_identical_lyrics_are_equal(self) -> None:
        text = "[ti: A]\n[00:01.000]x\n"
        assert Lyrics.loads(text) == Lyrics.loads(text)

    def test_metadata_difference_makes_them_unequal(self) -> None:
        """改前这里会判为相等 —— 拿 ``==`` 检查往返就是假阳性."""
        left = Lyrics.loads("[ti: A]\n[00:01.000]x\n")
        right = Lyrics.loads("[ti: B]\n[00:01.000]x\n")
        assert left != right

    def test_missing_metadata_makes_them_unequal(self) -> None:
        left = Lyrics.loads("[ti: A]\n[00:01.000]x\n")
        right = Lyrics.loads("[00:01.000]x\n")
        assert left != right

    def test_metadata_order_matters(self) -> None:
        """metadata 按全部条目比, 标签顺序也算数."""
        left = Lyrics.loads("[ti: A]\n[ar: B]\n[00:01.000]x\n")
        right = Lyrics.loads("[ar: B]\n[ti: A]\n[00:01.000]x\n")
        assert left != right

    def test_line_difference_makes_them_unequal(self) -> None:
        left = Lyrics.loads("[ti: A]\n[00:01.000]x\n")
        right = Lyrics.loads("[ti: A]\n[00:01.000]y\n")
        assert left != right

    def test_roundtrip_equality_is_a_real_check(self) -> None:
        lyrics = Lyrics.loads("[ti: A]\n[ti: B]\n[00:01.000]x\n")
        assert Lyrics.loads(lyrics.dumps()) == lyrics

    def test_slice_is_equal(self) -> None:
        lyrics = Lyrics.loads("[ti: A]\n[00:01.000]x\n")
        assert lyrics[:] == lyrics

    def test_plain_list_compares_lines_only(self) -> None:
        """列表没有 metadata 可比, 所以这一支沿用 ``UserList`` 的语义.

        于是会出现"两份 Lyrics 不相等, 但其中一份等于另一份的行列表"这种不对称,
        这是刻意的: 与列表比较时无从谈起 metadata.
        """
        left = Lyrics.loads("[ti: A]\n[00:01.000]x\n")
        right = Lyrics.loads("[ti: B]\n[00:01.000]x\n")
        assert left != right
        assert list(left) == list(right)
        assert left == list(right)

    def test_not_equal_to_unrelated_type(self) -> None:
        assert Lyrics.loads("[00:01.000]x\n") != 42
