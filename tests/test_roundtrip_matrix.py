"""往返保真度 (roundtrip fidelity) 测试矩阵 —— NEW-ROUNDTRIP.

本模块断言的是三条**不变量**, 而不是逐条硬编码输出:

1. ``parser-invariants``: 解析器产出的数据必须能通过自己的
   :func:`~lemony_lrc_parser.validate_lyrics` (error 级问题为零).
   解析器不应该产出自己的校验器会判为错误的数据.
2. ``dump-convergence``: :meth:`Lyrics.dumps` 最多一轮收敛, 即
   ``d2 = dumps(loads(d1))`` 与 ``d3 = dumps(loads(d2))`` 必须相等.
3. ``semantic-stability``: 对格式良好的语料, ``loads(dumps(x))`` 的行数、
   start / end、正文与参考行文本必须与首次解析结果一致.

语料由两部分组成: 手写用例 (可读、失败时能直接定位) 与固定种子的随机语料
(覆盖手写用例想不到的组合). 随机语料刻意包含病态构造 (1-4 位分钟、秒数 >= 60、
纯空白正文、重复/乱序标签), 因此只能当作问题的**上界**, 不代表真实文件里的
发生率.

已知有损场景 (不算 bug, 见各用例的 docstring 与 ``docs/feature-ideas.md``):
纯空白行、空正文 + 显式区间、方括号形式的逐字标签, 这三类不纳入不变量 3.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

import pytest

from lemony_lrc_parser import Lyrics, ParseOptions, SerializationOptions
from lemony_lrc_parser.cli import main

#: 逐字/行标签毫秒位数固定, 行间不留空行, 便于比对文本.
DUMPS_OPTS = SerializationOptions(with_metadata=True, line_separator="\n")

#: 格式良好的语料: 既要不变量 1 / 2 成立, 也要不变量 3 (行结构稳定) 成立.
WELL_FORMED_CORPUS: list[str] = [
    "",
    "\n",
    "[ti: Title]\n[ar: Artist]\n[00:01.000]Hello\n[00:02.000]World\n",
    "[00:01.000]Hello\n",
    "[00:01.000]Hello[00:02.000]World\n",
    "[00:01.000]Hello\n[00:02.000][00:03.000]Folded\n",
    "[00:01.000]Hello\n\n[00:02.000]World\n",
    "[00:01.000]Hello\n[00:01.000]你好\n",
    "[00:01.000]Hello\n[00:02.000]World\n[00:02.000]世界\n",
    "[00:01.000]Hello   \n[00:02.000]  World  \n",
    # 纯空白正文 (标签之后的空白算内容, 见 parser 的 2c 分支)
    "[00:01.000]   \n",
    "[00:01.000]a\n[00:02.000]  \n",
    "<00:02.000> \n",
    # 逐字 (Enhanced LRC / SPL)
    "[00:01.000]<00:01.000>Hello <00:01.500>world[00:02.000]\n",
    "[00:01.000]<00:01.500>Delayed[00:02.000]\n",
    "[00:01.000]<00:01.000>a<00:01.500>b<00:02.000>c[00:02.500]\n",
    "<00:01.000>No line tag\n",
    "<00:01.000>a<00:01.500>b\n",
    # 折叠标签与占位行
    "[00:01.000][00:02.000]Folded\n",
    "[00:01.000]\n[00:02.000]Later\n",
    "[00:01.000]Hello\n[00:02.000]\n[00:03.000]World\n",
    # 参考行
    "[00:01.000]Hello\n    你好\n[00:02.000]World\n",
    # metadata 往返
    "[ti: A] [ar: B]\n[00:01.000]x\n",
    "[ti:]\n[00:01.000]x\n",
    "[ti: value with : colon]\n[00:01.000]x\n",
    # 宽松时间标签
    "[0:1]x\n",
    "[1234:59.999]x\n[1234:59.999]y\n",
    "[00:59.999]x\n",
]

#: 已知有损 / 病态语料: 只要求不变量 1 / 2 (以及第一次解析不崩).
DEGENERATE_CORPUS: list[str] = [
    # 行首标签晚于首个词元 → 整行按既有策略丢弃 (B1)
    "[00:30.000]<00:10.000>hi\n翻译行\n",
    "[00:10.000]<00:05.000>text\n",
    # 行首是纯文本, 词元时间早于行标签 → end 归一化为 None
    "[00:10.000]a<00:05.000>b<00:06.000>\n",
    "[00:10.000] <00:05.000>\n",
    # 行尾标签与行首标签相同 → 零长度行, end 归一化为 None
    "[00:01.000]text[00:01.000]\n",
    # 空正文 + 显式区间: dumps 出 ``[start][end]``, 重新解析会变成两个占位行
    "<00:01.000><00:02.000>\n",
    # 秒数 >= 60 (宽松解析 + warning)
    "[00:99.000]x\n",
    # 乱序标签
    "[00:05.000]a<00:02.000>b<00:06.000>\n",
    # 只有一个行标签的孤儿行
    "no anchor at all\n",
]

ALL_CORPUS = WELL_FORMED_CORPUS + DEGENERATE_CORPUS


# ---------------------------------------------------------------------------
# 随机语料
# ---------------------------------------------------------------------------

_RANDOM_ATOMS = [
    "[00:01.000]",
    "[00:02.000]",
    "[00:05.000]",
    "[00:10.000]",
    "<00:01.000>",
    "<00:02.000>",
    "<00:05.000>",
    "<00:10.000>",
    "",
    " ",
    "  ",
    "a",
    "b",
    "hello",
    "歌词",
    "[ti: T]",
]


def _random_documents(count: int = 400, seed: int = 20240607) -> list[str]:
    """生成固定种子的随机语料 (可复现, 覆盖手写用例想不到的组合)."""
    rng = random.Random(seed)
    docs: list[str] = []
    for _ in range(count):
        lines = []
        for _ in range(rng.randint(1, 3)):
            lines.append(
                "".join(rng.choice(_RANDOM_ATOMS) for _ in range(rng.randint(1, 5)))
            )
        docs.append("\n".join(lines))
    return docs


RANDOM_CORPUS = _random_documents()


def _semantic_view(lyrics: Lyrics) -> list[tuple[object, ...]]:
    """只看"用户可见"的结构: 行时间范围、正文、参考行文本."""
    return [
        (
            line.start,
            line.end,
            line.text,
            tuple(ref.text for ref in line.reference_lines),
        )
        for line in lyrics
    ]


def _ids(corpus: list[str]) -> list[str]:
    return [f"{i:03d}-{doc!r}" for i, doc in enumerate(corpus)]


# ---------------------------------------------------------------------------
# 不变量 1: 解析器输出必须通过自己的校验器
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc", ALL_CORPUS + RANDOM_CORPUS, ids=_ids(ALL_CORPUS + RANDOM_CORPUS)
)
def test_parser_output_passes_its_own_validator(doc: str) -> None:
    """解析器产出的数据不应出现 error 级问题 (自己的校验器即规格)."""
    lyrics = Lyrics.loads(doc)
    errors = [issue for issue in lyrics.validate() if issue.severity == "error"]
    assert not errors, f"{doc!r} -> {[f'[{e.code}] {e.message}' for e in errors]}"


# ---------------------------------------------------------------------------
# 不变量 2: dumps 最多一轮收敛
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc", ALL_CORPUS + RANDOM_CORPUS, ids=_ids(ALL_CORPUS + RANDOM_CORPUS)
)
def test_dumps_converges_after_one_round(doc: str) -> None:
    """``dumps`` 必须是 (最多一轮之后的) 不动点, 否则解析↔序列化会持续漂移."""
    d1 = Lyrics.loads(doc).dumps(options=DUMPS_OPTS)
    d2 = Lyrics.loads(d1).dumps(options=DUMPS_OPTS)
    d3 = Lyrics.loads(d2).dumps(options=DUMPS_OPTS)
    assert d2 == d3, f"{doc!r}:\n  d1={d1!r}\n  d2={d2!r}\n  d3={d3!r}"
    # 第一轮就已经是定点时, 也顺带确认没有"用一次才稳定"的隐式漂移
    if d1 == d2:
        assert Lyrics.loads(d1) == Lyrics.loads(d2)


# ---------------------------------------------------------------------------
# 不变量 3: 格式良好的语料 dump→load 后行结构不变
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc", WELL_FORMED_CORPUS, ids=_ids(WELL_FORMED_CORPUS))
def test_well_formed_corpus_is_structurally_stable(doc: str) -> None:
    """格式良好的输入在 dump→load 之后, 行数 / 时间范围 / 文本必须不变."""
    before = Lyrics.loads(doc)
    after = Lyrics.loads(before.dumps(options=DUMPS_OPTS))
    assert _semantic_view(after) == _semantic_view(before)


@pytest.mark.parametrize("doc", WELL_FORMED_CORPUS, ids=_ids(WELL_FORMED_CORPUS))
def test_well_formed_corpus_metadata_roundtrips(doc: str) -> None:
    """格式良好的语料里, metadata 必须原样往返."""
    before = Lyrics.loads(doc)
    after = Lyrics.loads(before.dumps(options=DUMPS_OPTS))
    assert after.metadata == before.metadata


# ---------------------------------------------------------------------------
# 与解析选项的组合: 过滤 / 隐式行尾不应破坏上述不变量
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "options",
    [
        ParseOptions(),
        ParseOptions(fill_implicit_line_end=True),
        ParseOptions(line_filter="Hello"),
        ParseOptions(line_filter=""),
        ParseOptions(fill_implicit_line_end=True, line_filter="World|你好"),
    ],
    ids=["default", "fill_end", "filter-str", "filter-empty", "fill+filter"],
)
@pytest.mark.parametrize("doc", WELL_FORMED_CORPUS, ids=_ids(WELL_FORMED_CORPUS))
def test_options_do_not_break_invariants(doc: str, options: ParseOptions) -> None:
    """解析选项 (过滤 / 隐式行尾) 不应破坏校验器与收敛性不变量."""
    lyrics = Lyrics.loads(doc, options=options)
    errors = [issue for issue in lyrics.validate() if issue.severity == "error"]
    assert not errors, f"{doc!r} + {options!r} -> {[e.code for e in errors]}"

    d1 = lyrics.dumps(options=DUMPS_OPTS)
    d2 = Lyrics.loads(d1).dumps(options=DUMPS_OPTS)
    d3 = Lyrics.loads(d2).dumps(options=DUMPS_OPTS)
    assert d2 == d3, f"{doc!r} + {options!r}:\n  d2={d2!r}\n  d3={d3!r}"
    # 过滤 + 隐式行尾组合下, 补齐的 end 不应违反 end > start
    for line in lyrics:
        assert line.end is None or line.end > line.start


# ---------------------------------------------------------------------------
# 字幕互转: cue 数量不应凭空变化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc", WELL_FORMED_CORPUS, ids=_ids(WELL_FORMED_CORPUS))
def test_subtitle_export_keeps_cue_count(doc: str) -> None:
    """LRC → SRT / WebVTT → LRC 时 cue 数量必须保持 (逐字标签/metadata 会丢).

    字幕没有"行尾空白"的概念, cue 文本行在导出与重新解析时都会被 rstrip,
    因此这里按 rstrip 之后比较 (这是格式差异, 不是本库的往返缺陷).
    """
    lyrics = Lyrics.loads(doc)
    for exported, back in (
        (lyrics.to_srt(), Lyrics.from_srt),
        (lyrics.to_webvtt(), Lyrics.from_webvtt),
    ):
        reparsed = back(exported)
        assert len(reparsed) == len(lyrics), f"{doc!r}:\n{exported!r}"
        # 不用 zip(..., strict=True): 该参数需要 Python 3.10+, 本库仍支持 3.9
        for line, restored in zip(lyrics, reparsed):
            assert restored.start == line.start
            assert restored.text == line.text.rstrip()


# ---------------------------------------------------------------------------
# 已知有损场景 / 本轮修复的行为规格 (不纳入上面三条不变量)
# ---------------------------------------------------------------------------


class TestKnownLossyBehaviors:
    """把"已知有损"写成显式规格, 避免它们悄悄扩散成默认行为."""

    def test_empty_text_with_range_becomes_two_placeholders(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """空正文 + 显式区间: 写出 ``[start][end]``, 重新解析变成两个占位行.

        LRC 里没有"空正文但带区间"的无歧义写法, 因此这里选择保留 end 并告警
        (与 metadata 的 warn-but-write 策略一致), 而不是静默丢掉区间.
        """
        lyrics = Lyrics.loads("<00:01.000><00:02.000>")
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (1000, 2000, "")
        ]

        with caplog.at_level(logging.WARNING):
            dumped = lyrics.dumps(options=DUMPS_OPTS)
        assert dumped == "[00:01.000][00:02.000]\n"
        assert "no text" in caplog.text

        reparsed = Lyrics.loads(dumped)
        assert [(line.start, line.end, line.text) for line in reparsed] == [
            (1000, None, ""),
            (2000, None, ""),
        ]

    def test_bracket_byword_tag_duplicates_line_on_reparse(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``use_bracket_for_byword_tag=True`` + 首词元延迟起唱 → 行被拆成两行.

        该写法在 LRC 里与"折叠行标签"无法区分, 属选项自身代价; 这里确保它至少
        有告警、且行为被记录下来.
        """
        lyrics = Lyrics.loads("[00:01.000]<00:01.500>hello")
        with caplog.at_level(logging.WARNING):
            dumped = lyrics.dumps(
                options=SerializationOptions(
                    use_bracket_for_byword_tag=True,
                    with_metadata=False,
                    line_separator="\n",
                )
            )
        assert dumped == "[00:01.000][00:01.500]hello\n"
        assert "split this line into two" in caplog.text

        reparsed = Lyrics.loads(dumped)
        assert [line.text for line in reparsed] == ["hello", "hello"]

        # 默认 (尖括号) 写法没有这个问题
        assert Lyrics.loads(lyrics.dumps(options=DUMPS_OPTS)) == lyrics

    def test_late_leading_tag_is_clamped_not_dropped(self) -> None:
        """行首标签晚于首个词元时归位保留 (本行与翻译行都不丢).

        这曾经是"整行丢弃 + 后续翻译行变孤儿"的取舍 (B1 的旧行为); 现在标签被
        归位到首个词元时间, 只有标签本身被丢弃.
        """
        lyrics = Lyrics.loads("[00:30.000]<00:10.000>hi\n翻译行\n")
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (10000, None, "hi")
        ]
        assert [r.text for r in lyrics[0].reference_lines] == ["翻译行"]

    def test_zero_length_line_loses_its_end_not_its_text(self) -> None:
        """``[00:01.000]text[00:01.000]`` → 零长度区间, end 被丢弃, 文本保留."""
        lyrics = Lyrics.loads("[00:01.000]text[00:01.000]")
        assert [(line.start, line.end, line.text) for line in lyrics] == [
            (1000, None, "text")
        ]


class TestInferredEndIsNeverDegenerate:
    """A1 回归: 解析器不得产出 ``end <= start`` (那是 validate 眼里的 error)."""

    @pytest.mark.parametrize(
        "doc",
        [
            "[00:10.000]a<00:05.000>b<00:06.000>",
            "[00:10.000] <00:05.000>",
            "[00:10.000]a<00:05.000>b[00:06.000]",
            "[00:01.000]text[00:01.000]",
            "[00:05.000]b[00:05.000][00:05.000]",
        ],
    )
    def test_degenerate_inferred_end_is_discarded(
        self, doc: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """末词元推断出的 end 与行首矛盾时置回 None, 并给出 warning."""
        with caplog.at_level(logging.WARNING):
            lyrics = Lyrics.loads(doc)
        assert len(lyrics) == 1
        line = lyrics[0]
        assert line.end is None or line.end > line.start
        assert line.end is None
        assert "discarding the inferred end" in caplog.text
        # 词元自身的时间戳原样保留, 不因归一化而丢数据
        assert line.content[-1].end is not None

    def test_usable_byword_line_keeps_its_end(self) -> None:
        """正常逐字行不受影响: 行尾仍取末词元的 end."""
        lyrics = Lyrics.loads("[00:01.000]<00:01.000>a<00:02.000>b[00:03.000]")
        line = lyrics[0]
        assert (line.start, line.end) == (1000, 3000)

    def test_cli_validate_accepts_what_the_parser_produces(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """解析器写出的文件, CLI ``validate --strict`` 不应因 error 而失败.

        残留的 ``token-before-line-start`` 是 warning (数据本身确实自相矛盾),
        所以这里只要求没有 ``[ERROR]``; 这既守住不变量 1, 也保住了"宽松解析 +
        可诊断"的取向.
        """
        path = tmp_path / "self-produced.lrc"
        path.write_text(
            Lyrics.loads("[00:10.000]a<00:05.000>b<00:06.000>").dumps(),
            encoding="utf-8",
        )
        rc = main(["validate", "--strict", str(path)])
        captured = capsys.readouterr()
        assert rc == 0, captured.err
        assert "[ERROR]" not in captured.err
        assert "token-before-line-start" in captured.err


class TestWhitespaceContentRoundtrip:
    """A5a 回归: 标签之后的纯空白算正文, 不能被解析成空占位行."""

    @pytest.mark.parametrize(
        "doc, expected_text",
        [
            ("[00:01.000]   ", "   "),
            ("[00:01.000]a\n[00:02.000]  ", "  "),
            ("<00:02.000> ", " "),
        ],
    )
    def test_whitespace_only_content_is_preserved(
        self, doc: str, expected_text: str
    ) -> None:
        lyrics = Lyrics.loads(doc)
        assert lyrics[-1].text == expected_text
        reparsed = Lyrics.loads(lyrics.dumps(options=DUMPS_OPTS))
        assert _semantic_view(reparsed) == _semantic_view(lyrics)

    def test_bare_whitespace_line_is_still_a_separator(self) -> None:
        """没有标签的空白行仍是分隔符 (重置参考行锚点), 不产生空歌词行."""
        lyrics = Lyrics.loads("[00:01.000]a\n   \n翻译行\n")
        assert len(lyrics) == 1
        assert lyrics[0].text == "a"
        assert lyrics[0].reference_lines == []
