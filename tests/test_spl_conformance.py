"""SPL 一致性测试 —— 逐条对照 SPL 语法标准.

标准: https://moriafly.com/standards/spl.html (制定 2024-12-16, 修订 2026-09-19)

SPL (Salt Player Lyrics) 是 LRC 的超集, 也是目前唯一把"LRC 家族多年踩到的兼容
性问题"写成条文的文档, 因此本库把它当作 LRC 语义的参照物. 这个模块把标准的每一条
可判定规则都钉成一个用例, 并在 docstring 里写明标准原文的要点, 这样以后再有人问
"为什么空行不产生歌词行"时, 答案在测试里而不是在某个人脑子里.

本模块**不**追求覆盖所有 LRC 用法 (那些在 test_parser_full.py / test_line_parser.py),
只覆盖"标准说了什么"这一层.
"""

from __future__ import annotations

import logging

import pytest

from lemony_lrc_parser import Lyrics, SerializationOptions, parse_lrc

#: 行间不留空行, 便于断言写出的文本.
DUMPS_OPTS = SerializationOptions(with_metadata=False, line_separator="\n")


def _view(lyrics: Lyrics) -> list[tuple[object, ...]]:
    """用户可见结构: 行范围 + 正文 + 参考行文本."""
    return [
        (
            line.start,
            line.end,
            line.text,
            tuple(ref.text for ref in line.reference_lines),
        )
        for line in lyrics
    ]


# ---------------------------------------------------------------------------
# 时间戳的数字规范
# ---------------------------------------------------------------------------


class TestTimestampDigits:
    """标准: 分 1-3 位, 秒 1-2 位, 毫秒 1-6 位; 不足 3 位的毫秒视为在后位省略 0."""

    @pytest.mark.parametrize(
        ("tag", "expected_ms"),
        [
            ("[103:3.405]", 103 * 60_000 + 3 * 1000 + 405),
            ("[3:12.5]", 3 * 60_000 + 12 * 1000 + 500),
            ("[1:1.1]", 60_000 + 1000 + 100),
            ("[00:01.02]", 1000 + 20),
            ("[00:01.2]", 1000 + 200),
            ("[0:0.000000]", 0),
        ],
    )
    def test_digit_widths_and_left_padding(self, tag: str, expected_ms: int) -> None:
        """标准明说 ``1`` 是 100 毫秒而不是 1 毫秒, ``02`` 是 20 毫秒."""
        lyrics = parse_lrc(f"{tag}x")
        assert [line.start for line in lyrics] == [expected_ms]

    def test_wrong_bracket_is_not_a_timestamp(self) -> None:
        """标准把 ``(103:3.405)`` 列为错误写法: 不是时间标签, 也就没有锚点.

        实际行为是"无锚点的孤儿行被丢弃" (宽松解析 + warning), 不产生歌词行.
        """
        assert _view(parse_lrc("(103:3.405)wrong")) == []

    def test_three_digit_seconds_is_not_a_timestamp(self) -> None:
        """标准把 ``[3:102.5]`` 列为错误写法 (秒超 2 位)."""
        assert _view(parse_lrc("[3:102.5]wrong")) == []

    def test_minute_with_four_digits_is_accepted_leniently(self) -> None:
        """本库比标准宽松: 标准限制分 1-3 位, 这里 4 位也照收 (不静默丢弃).

        真实语料里 4 位分钟出现 0 次, 宽松接收只是为了"坏数据也尽量读出来".
        """
        lyrics = parse_lrc("[1234:00.000]x")
        assert [line.start for line in lyrics] == [1234 * 60_000]

    def test_long_millisecond_field_is_read_as_a_fraction(self) -> None:
        """标准允许毫秒写 1-6 位; 本库按"秒的小数部分"读, 截断到毫秒.

        ``450000`` 既可读成 450000 毫秒 (标准字面), 也可读成 0.450000 秒 = 450
        毫秒 (与"不足 3 位右补 0"同源的读法). 后者才是写文件的人的本意, 因此
        截断而不是放大到 7.5 分钟. 真实语料里 4-6 位毫秒出现 0 次.
        """
        assert [line.start for line in parse_lrc("[00:01.450000]x")] == [1450]
        assert [line.start for line in parse_lrc("[00:01.1234]x")] == [1123]

    def test_long_millisecond_fields_do_not_collide(self) -> None:
        """截断后两行仍可能落到同一时间点, 此时后一行变成参考行 (翻译).

        这是上面那条读法的已知代价, 记录在此以免以后误以为是新 bug.
        """
        lyrics = parse_lrc("[00:01.1234]F\n[00:01.12345]G\n")
        assert _view(lyrics) == [(1123, None, "F", ("G",))]


# ---------------------------------------------------------------------------
# 歌词行: 显式/隐式行尾
# ---------------------------------------------------------------------------


class TestLineEnd:
    """标准: 行尾可写在同行内, 也可写成独立的空标记行; 未标则持续到下一行开始."""

    def test_inline_line_end(self) -> None:
        """``[05:20.22]你好[05:21.22]``: 末尾时间戳是结束时间."""
        assert _view(parse_lrc("[05:20.22]hello[05:21.22]")) == [
            (320220, 321220, "hello", ())
        ]

    def test_standalone_end_marker(self) -> None:
        """标准: "时间戳后不接任何文本内容的行是纯粹的结束标记"."""
        lyrics = parse_lrc("[05:20.22]hello\n[05:21.22]\n[05:30.22]world\n")
        assert _view(lyrics) == [
            (320220, 321220, "hello", ()),
            (330220, None, "world", ()),
        ]

    def test_end_marker_sharing_timestamp_with_next_line(self) -> None:
        """标准: 结束标记常与下一句同时间戳, 二者不冲突, 下一句是独立歌词行.

        这条是真实语料里踩得最狠的坑 (138 个文件 / 420 行): 曾经的实现会为结束
        标记造一条空歌词行, 于是同时间戳的真实歌词被挂成它的参考行 (翻译),
        按 ``line.text`` 遍历的消费者整行丢失.
        """
        lyrics = parse_lrc("[05:20.22]hello\n[05:21.22]\n[05:21.22]world\n")
        assert _view(lyrics) == [
            (320220, 321220, "hello", ()),
            (321220, None, "world", ()),
        ]

    def test_end_marker_does_not_join_translation_recognition(self) -> None:
        """标准: 结束标记"不参与翻译识别", 不是主歌词也不是翻译文本."""
        lyrics = parse_lrc("[00:01.000]main\n[00:02.000]\n[00:02.000]trans\n")
        assert _view(lyrics) == [(1000, 2000, "main", ()), (2000, None, "trans", ())]

    def test_end_marker_without_target_is_dropped(self) -> None:
        """文件首行的空标记没有可收尾的上一行 → 忽略, 不产生歌词行."""
        assert _view(parse_lrc("[00:00.000]\n[00:01.000]hello\n")) == [
            (1000, None, "hello", ())
        ]

    def test_inline_end_wins_over_a_later_marker(self) -> None:
        """同行内的行尾标签优先: 已有的显式区间不被后面的标记改写."""
        assert _view(parse_lrc("[00:10.000]a[00:15.000]\n[00:20.000]\n")) == [
            (10000, 15000, "a", ())
        ]

    def test_implicit_line_end_is_opt_in(self) -> None:
        """标准把"持续到下一行开始"当默认语义; 本库默认留 ``end=None`` (未知).

        需要标准语义时用 ``ParseOptions(fill_implicit_line_end=True)``; 字幕导出
        默认就是这种语义 (``SubtitleOptions.fill_end_from_next`` 默认为真).
        """
        from lemony_lrc_parser import ParseOptions

        lrc = "[05:20.22]hello\n[05:22.22]world\n"
        assert [line.end for line in parse_lrc(lrc)] == [None, None]
        filled = parse_lrc(lrc, options=ParseOptions(fill_implicit_line_end=True))
        assert [line.end for line in filled] == [322220, None]


# ---------------------------------------------------------------------------
# 重复行 / 翻译
# ---------------------------------------------------------------------------


class TestRepeatedLinesAndTranslations:
    """标准: 多时间戳简写重复行; 翻译靠同时间戳或"紧跟主行且省略时间戳"识别."""

    def test_folded_repeated_line(self) -> None:
        lyrics = parse_lrc("[05:20.22][05:30.22]hello\n")
        assert _view(lyrics) == [
            (320220, None, "hello", ()),
            (330220, None, "hello", ()),
        ]

    def test_translation_by_same_timestamp(self) -> None:
        lyrics = parse_lrc("[05:20.22]main\n[05:20.22]trans\n")
        assert _view(lyrics) == [(320220, None, "main", ("trans",))]

    def test_translation_need_not_be_adjacent(self) -> None:
        """标准: 同时间戳的两句可以不紧挨着, 但翻译须在主歌词之后."""
        lyrics = parse_lrc("[05:20.22]main\n[05:25.22]other\n[05:20.22]trans\n")
        assert _view(lyrics) == [
            (320220, None, "main", ("trans",)),
            (325220, None, "other", ()),
        ]

    def test_translation_without_timestamp(self) -> None:
        """标准: 省略时间戳的翻译"必须紧挨着主歌词句子"."""
        lyrics = parse_lrc("[05:20.22]main\n[05:21.22]other\nHello\n")
        assert _view(lyrics) == [
            (320220, None, "main", ()),
            (321220, None, "other", ("Hello",)),
        ]

    def test_multi_line_translation(self) -> None:
        """标准: 支持多行翻译 (连续多条无标签行都归主行)."""
        lyrics = parse_lrc("[05:20.22]main\nHello\nこんにちは\n")
        assert _view(lyrics) == [(320220, None, "main", ("Hello", "こんにちは"))]


# ---------------------------------------------------------------------------
# 逐字歌词
# ---------------------------------------------------------------------------


class TestByword:
    """标准: 逐字标记用 ``[...]``, 兼容写法 ``<...>``; 必须递增且落在行区间内."""

    @pytest.mark.parametrize(
        "line",
        [
            "[05:20.22]你好[05:23.22]椒盐音乐[05:24.22]",
            "[05:20.22]你好<05:23.22>椒盐音乐[05:24.22]",
        ],
        ids=["bracket", "angle"],
    )
    def test_both_bracket_styles(self, line: str) -> None:
        """两种写法等价; 行尾标签同时是最后一个词元的结束时间."""
        lyrics = parse_lrc(f"{line}\n")
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("你好", None, 323220),
            ("椒盐音乐", 323220, 324220),
        ]
        assert (lyrics[0].start, lyrics[0].end) == (320220, 324220)

    def test_delayed_first_word(self) -> None:
        """标准 (2026-09-19 修订新增): ``[行标签]<首字标签>文本`` 实现"到达而未起唱"."""
        lyrics = parse_lrc("[05:20.22]<05:21.22>你好<05:23.22>椒盐音乐[05:24.22]\n")
        assert (lyrics[0].start, lyrics[0].end) == (320220, 324220)
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("你好", 321220, 323220),
            ("椒盐音乐", 323220, 324220),
        ]

    def test_out_of_order_marker_is_ignored(self) -> None:
        """标准: "小于之前的时间戳"的标记被忽略 (文本合并, 不丢字)."""
        lyrics = parse_lrc("[05:20.22]a<05:23.22>b<05:21.22>c<05:24.22>\n")
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("a", None, 323220),
            ("bc", 323220, 324220),
        ]

    def test_marker_before_line_start_is_ignored(self) -> None:
        """标准: 不在"行开始时间和结束时间间"的标记被忽略, 行标签为准."""
        lyrics = parse_lrc("[05:20.22]<05:10.22>hello<05:23.22>world[05:24.22]\n")
        assert (lyrics[0].start, lyrics[0].end) == (320220, 324220)
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("hello", None, 323220),
            ("world", 323220, 324220),
        ]

    def test_marker_after_line_end_is_ignored(self) -> None:
        """标准: 晚于行尾的标记被忽略, 行尾标签保留 (不反过来丢掉行尾)."""
        lyrics = parse_lrc("[05:20.22]a<05:23.22>b<05:25.22>c[05:24.22]\n")
        assert (lyrics[0].start, lyrics[0].end) == (320220, 324220)
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("a", None, 323220),
            ("bc", 323220, 324220),
        ]

    def test_folded_plus_byword_is_read_as_repeated_lines(self) -> None:
        """标准"局限性"一节: 逐字与重复行简写不兼容, 第二行的标记因越界被忽略.

        注意判据: 整行标签**出现递减**才按重复行读. 若标签非递减, 那就是
        ``[行标签][首字标签]文本`` 形态的逐字行 (真实语料里 199 行有 197 行
        是后者), 见 :func:`test_bracket_prefix_is_read_as_delayed_first_word`.
        """
        lyrics = parse_lrc("[05:20.22][05:30.22]你好[05:23.22]椒盐音乐[05:24.22]\n")
        assert _view(lyrics) == [
            (320220, 324220, "你好椒盐音乐", ()),
            (330220, None, "你好椒盐音乐", ()),
        ]
        assert [(t.content, t.start, t.end) for t in lyrics[1].content] == [
            ("你好椒盐音乐", None, None)
        ]

    def test_bracket_prefix_is_read_as_delayed_first_word(self) -> None:
        """``[行标签][首字标签]文本`` 且标签非递减 → 首字延迟的逐字行 (一行).

        这是本库相对标准"局限性"一节的**有意偏离**: 真实语料里 199 行这种写法
        有 197 行的两个行首标签只差 0.1-1.3 秒, 按重复行读会得到两条几乎相同的
        行. 写出时本库会把它规范化成标准的写法 (中间标记 ``<...>``、行尾 ``[...]``).
        """
        lyrics = parse_lrc("[00:05.650][00:05.730]徘[00:06.130]徊[00:06.450]\n")
        assert len(lyrics) == 1
        assert [(t.content, t.start, t.end) for t in lyrics[0].content] == [
            ("", 5650, 5730),
            ("徘", 5730, 6130),
            ("徊", 6130, 6450),
        ]
        dumped = lyrics.dumps(options=DUMPS_OPTS)
        assert dumped == "[00:05.650]<00:05.730>徘<00:06.130>徊[00:06.450]\n"


# ---------------------------------------------------------------------------
# 本库的扩展与偏离 (标准没写, 或标准与真实语料冲突的地方)
# ---------------------------------------------------------------------------


class TestDocumentedDeviations:
    """把"标准没说 / 说了但真实数据另有共识"的地方钉成规格."""

    def test_whitespace_only_body_is_content(self) -> None:
        """标签之后只剩空白算正文 (A5a), 不算"没有文本内容".

        标准只写了"不接任何文本内容", 没有定义空白; 本库选择把它当内容, 否则
        ``dumps`` 写出的 ``[00:01.000]  `` 无法往返.
        """
        assert _view(parse_lrc("[00:01.000]  \n")) == [(1000, None, "  ", ())]

    def test_angle_only_empty_line_is_kept(self) -> None:
        """整行只有尖括号标签时保留为一条空正文行 (承载空 SRT cue).

        标准里的尖括号是逐字标记, 空正文行在 SPL 里并不存在; 但 LRC 家族需要一个
        能无歧义表达"空 cue"的写法, 本库沿用 Enhanced LRC 的行首尖括号形式, 并且
        ``dumps`` 也用同一形式写回 (用方括号写会被读成上一行的结束标记).
        """
        lyrics = parse_lrc("<00:01.000><00:02.000>\n")
        assert _view(lyrics) == [(1000, 2000, "", ())]
        assert lyrics.dumps(options=DUMPS_OPTS) == "<00:01.000><00:02.000>\n"

    def test_text_less_reference_line_is_not_written(self) -> None:
        """没有正文的参考行无法在 LRC 里表达 → 不写出 (有 debug 日志).

        标准会把 ``[00:01.000]<00:01.500><00:02.000>`` 读成上一行的结束标记,
        因此这种参考行写出后必然被读成别的东西.
        """
        from lemony_lrc_parser import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics(
            [
                LyricLine(
                    start=1000,
                    content=BasicLyricLine([LyricToken(content="Main")]),
                    reference_lines=[
                        BasicLyricLine([LyricToken(content="", start=1500, end=2000)])
                    ],
                )
            ]
        )
        assert lyrics.dumps(options=DUMPS_OPTS) == "[00:01.000]Main\n"

    def test_seconds_at_or_above_sixty_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """秒数 >= 60 按字面折算并 warning (标准只限制了位数, 没规定取值范围)."""
        with caplog.at_level(logging.WARNING):
            lyrics = parse_lrc("[00:99.000]x\n")
        assert [line.start for line in lyrics] == [99000]
        assert "seconds >= 60" in caplog.text
