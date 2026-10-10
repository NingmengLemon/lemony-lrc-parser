"""性质测试 (property-based tests).

手写用例只覆盖想得到的形状; 这里用 hypothesis 生成结构化歌词与随意拼接的 LRC 文本,
钉住几条无论输入长什么样都必须成立的性质. hypothesis 找到反例时会自动缩到最小,
并把它记进 ``.hypothesis/`` (已 gitignore), 下次优先重放.

生成器只造"本库能用 LRC 无损表达"的结构 (正文不含方括号 / 尖括号 / 换行, 开始时间
各不相同, 行尾晚于行首, metadata value 首尾无空白), 因为有损场景已经由
``test_roundtrip_matrix.py`` 的 ``TestKnownLossyBehaviors`` 显式钉住.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lemony_lrc_parser import (
    BasicLyricLine,
    LyricLine,
    Lyrics,
    LyricToken,
    Metadata,
    SerializationOptions,
    TimestampOverflowError,
    TimestampUnderflowError,
    format_timetag,
    parse_timetag,
)
from lemony_lrc_parser.timetag import MAX_TIMESTAMP_MS

#: 写出时不带行间空行: 空行会重置参考行锚点, 与这里的生成器无关, 只会制造噪音.
DUMPS = SerializationOptions(line_separator="")

#: 时间范围: 0 到 99 分钟. 更大的分钟数也合法, 但对性质没有额外信息量.
MAX_MS = 99 * 60_000

# ---------------------------------------------------------------------------
# 生成器
# ---------------------------------------------------------------------------

#: 正文字符: 不含 LRC 语法字符与换行; 带上空格、中日文与全角符号.
_TEXT_ALPHABET = st.sampled_from(
    list("abcxyzABC0123 ,.!?'-:;") + list("歌词雨の夜、。") + ["\u3000"]
)

#: 一段正文 (逐字词元或整行). 不允许只有空白: 那种行由
#: ``test_roundtrip_matrix.py`` 的空白用例单独覆盖.
texts = st.text(_TEXT_ALPHABET, min_size=1, max_size=12).filter(lambda s: s.strip())

metadata_keys = st.from_regex(r"\A[a-zA-Z][a-zA-Z0-9]{0,15}\Z")
metadata_values = st.text(st.sampled_from(list("abc XYZ 01:.()-歌")), max_size=12).map(
    str.strip
)
metadata = st.lists(st.tuples(metadata_keys, metadata_values), max_size=4).map(Metadata)


@st.composite
def lyric_lines(draw: st.DrawFn, start: int) -> LyricLine:
    """一行歌词: 整行正文或逐字词元, 可选行尾, 可选参考行."""
    end = draw(st.none() | st.integers(start + 1, start + 20_000))
    if draw(st.booleans()):
        content = BasicLyricLine([LyricToken(content=draw(texts))])
    else:
        # 逐字行: 首个词元从行首开始, 词元时间严格递增且不越过行尾.
        upper = end if end is not None else start + 20_000
        count = draw(st.integers(1, min(4, upper - start)))
        offsets = draw(
            st.lists(
                st.integers(start + 1, upper),
                min_size=count,
                max_size=count,
                unique=True,
            ).map(sorted)
        )
        starts = [start, *offsets[:-1]]
        tokens = [
            LyricToken(content=draw(texts), start=token_start, end=token_end)
            for token_start, token_end in zip(starts, offsets)
        ]
        content = BasicLyricLine(tokens)
        # 逐字行末尾的标签同时是末词元的 end 与行尾 (解析器据此推断行尾),
        # 所以"词元有 end 而行没有 end"在 LRC 里写不出来.
        if end is None:
            end = offsets[-1]
    references = draw(
        st.lists(
            texts.map(lambda text: BasicLyricLine([LyricToken(content=text)])),
            max_size=2,
        )
    )
    return LyricLine(start=start, end=end, content=content, reference_lines=references)


@st.composite
def lyrics_objects(draw: st.DrawFn) -> Lyrics:
    starts = draw(st.lists(st.integers(0, MAX_MS), max_size=6, unique=True).map(sorted))
    lines = [draw(lyric_lines(start)) for start in starts]
    return Lyrics(lines=lines, metadata=draw(metadata))


#: 随意拼接的 LRC 片段, 用来喂"什么输入都不能把解析器搞崩"那类性质.
_ATOMS = [
    "[00:01.000]",
    "[00:01.00]",
    "[00:02.5]",
    "[01:00]",
    "[00:99.000]",
    "<00:01.000>",
    "<00:02.000>",
    "<00:00.500>",
    "[ti: T]",
    "[ar: a [b]]",
    "[offset: 100]",
    "[x: 50% ]off]",
    "[",
    "]",
    "<",
    "a",
    "歌",
    " ",
    "\t",
    "\n",
    "\r\n",
    "\ufeff",
]
lrc_texts = st.lists(st.sampled_from(_ATOMS), max_size=30).map("".join)


def _view(lyrics: Lyrics) -> list[tuple[object, ...]]:
    """用户可见的结构: 行时间范围、正文、参考行正文."""
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
# 时间标签
# ---------------------------------------------------------------------------


@given(st.integers(0, MAX_TIMESTAMP_MS), st.integers(1, 6))
def test_timetag_roundtrip_within_precision(ms: int, tail_digits: int) -> None:
    """``parse(format(ms))`` 只丢掉尾数位数表达不了的精度, 不多不少."""
    tag = format_timetag(ms, use_angle_bracket=False, tail_digits=tail_digits)
    unit = 10 ** max(0, 3 - tail_digits)
    assert parse_timetag(tag) == ms - ms % unit


@given(st.integers(MAX_TIMESTAMP_MS + 1, 10**12))
def test_timetag_refuses_what_it_cannot_read_back(ms: int) -> None:
    """超出范围就报错, 而不是写出解析器读不回来的标签."""
    with pytest.raises(TimestampOverflowError):
        format_timetag(ms, use_angle_bracket=False, tail_digits=3)


# ---------------------------------------------------------------------------
# 序列化往返
# ---------------------------------------------------------------------------


@given(lyrics_objects())
def test_dumps_preserves_user_visible_structure(lyrics: Lyrics) -> None:
    """能用 LRC 表达的结构, ``dumps`` 再 ``loads`` 之后行、正文、参考行都不变."""
    reparsed = Lyrics.loads(lyrics.dumps(options=DUMPS))
    assert _view(reparsed) == _view(lyrics)
    assert reparsed.metadata == lyrics.metadata


@given(lyrics_objects())
def test_dumps_is_a_fixed_point_after_one_parse(lyrics: Lyrics) -> None:
    """解析过一次之后, ``loads(dumps(x)) == x`` 严格成立 (含词元时间与 metadata)."""
    once = Lyrics.loads(lyrics.dumps(options=DUMPS))
    twice = Lyrics.loads(once.dumps(options=DUMPS))
    assert twice == once


@given(lyrics_objects())
def test_dict_roundtrip(lyrics: Lyrics) -> None:
    """``from_dict(to_dict(x))`` 只丢 metadata 的重复项 (``to_dict`` 是有损的 dict 视角)."""
    restored = Lyrics.from_dict(lyrics.to_dict())
    assert list(restored) == list(lyrics)
    assert restored.metadata.to_pairs() == list(lyrics.metadata.items())


# ---------------------------------------------------------------------------
# 任意输入
# ---------------------------------------------------------------------------


@given(lrc_texts)
def test_parser_output_is_always_valid(text: str) -> None:
    """任何输入都不能让解析器产出 ``validate()`` 判为 error 的数据."""
    lyrics = Lyrics.loads(text)
    errors = [issue for issue in lyrics.validate() if issue.severity == "error"]
    assert not errors, [f"[{issue.code}] {issue.message}" for issue in errors]


@given(lrc_texts)
def test_dumps_converges_on_arbitrary_input(text: str) -> None:
    """``dumps`` 至多一轮收敛, 不会在解析与序列化之间来回漂移."""
    d1 = Lyrics.loads(text).dumps(options=DUMPS)
    d2 = Lyrics.loads(d1).dumps(options=DUMPS)
    assert Lyrics.loads(d2).dumps(options=DUMPS) == d2


# ---------------------------------------------------------------------------
# 变换
# ---------------------------------------------------------------------------


@given(lyrics_objects(), st.integers(-MAX_MS, MAX_MS), st.integers(-MAX_MS, MAX_MS))
def test_apply_delta_is_additive(lyrics: Lyrics, a: int, b: int) -> None:
    """``apply_delta(a).apply_delta(b) == apply_delta(a + b)``, 且不改原对象.

    任一路径中途出现负时间戳都会抛 ``TimestampUnderflowError``; 两条路径的中间值
    不同 (分步时 ``+a`` 可能先下溢), 所以这类组合不比较, 直接跳过.
    """
    before = lyrics.copy()
    try:
        stepwise = lyrics.apply_delta(a).apply_delta(b)
        combined = lyrics.apply_delta(a + b)
    except TimestampUnderflowError:
        return
    assert stepwise == combined
    assert lyrics == before


@given(lyrics_objects(), lyrics_objects())
def test_combine_does_not_mutate_inputs(main: Lyrics, other: Lyrics) -> None:
    main_before, other_before = main.copy(), other.copy()
    main.combine(other)
    main.combine(other, other_as_refline_only=False)
    _ = main + other
    assert main == main_before
    assert other == other_before


@given(lyrics_objects(), lyrics_objects())
def test_combine_never_drops_main_lines(main: Lyrics, other: Lyrics) -> None:
    """主歌词的每一行都留在合并结果里, 正文与时间不变."""
    combined = main.combine(other)
    assert [(line.start, line.text) for line in combined] == [
        (line.start, line.text) for line in main
    ]


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------


@given(st.lists(st.tuples(metadata_keys, metadata_values), max_size=8))
def test_metadata_views_agree(pairs: list[tuple[str, str]]) -> None:
    """dict 视角就是"同名取最后一次"的 dict; 无损视角就是原始条目."""
    meta = Metadata(pairs)
    assert meta.to_pairs() == pairs
    assert dict(meta) == dict(pairs)
    assert list(meta.items()) == list(dict(meta).items())
    assert len(meta) == len(dict(pairs))
    for key in meta:
        assert meta.getlist(key) == [v for k, v in pairs if k == key]
