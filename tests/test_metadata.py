"""测试 metadata 容器 (:class:`~lemony_lrc_parser.metadata.Metadata`).

这个容器有三套读法, 用例按读法分组, 每组都钉住"哪一种是有损的、哪一种是保真的",
免得以后有人顺手把其中一套改成另一套的语义:

* dict 视角 (``meta["ti"]`` / ``dict(meta)`` / ``.keys()``): 同名取**最后**一次,
  与 0.4.x 的裸 ``dict`` 行为一致。
* 无损视角 (``items()`` / ``to_pairs()`` / ``getlist()``): 全部条目, 含重复。
* 写入 (``add`` 追加 / ``set`` 替换): 保真路径与去重路径分开, 不靠参数开关。
"""

from __future__ import annotations

import pytest

from lemony_lrc_parser import Lyrics, Metadata, ProgrammingError, SerializationOptions

DUPLICATED = [("ti", "A"), ("ar", "X"), ("ti", "B")]


def _sample() -> Metadata:
    return Metadata(DUPLICATED)


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------


class TestConstruction:
    """从 dict / Metadata / pair 序列构造."""

    def test_empty(self) -> None:
        meta = Metadata()
        assert len(meta) == 0
        assert meta.to_pairs() == []
        assert not meta

    def test_from_dict_keeps_order(self) -> None:
        meta = Metadata({"b": "2", "a": "1"})
        assert meta.to_pairs() == [("b", "2"), ("a", "1")]

    def test_from_pairs_keeps_duplicates(self) -> None:
        assert _sample().to_pairs() == DUPLICATED

    def test_from_metadata_copies(self) -> None:
        """传 Metadata 是拷贝, 不是共享内部列表."""
        source = _sample()
        clone = Metadata(source)
        assert clone == source
        clone.add("mu", "Z")
        assert source.getlist("mu") == []

    @pytest.mark.parametrize("bad", ["ab", b"ab", 42])
    def test_rejects_non_pairs(self, bad: object) -> None:
        """裸字符串 / 数字这类输入应当当场报错, 而不是被拆成字符对."""
        with pytest.raises(ProgrammingError):
            Metadata(bad)  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# dict 视角 (有损)
# ---------------------------------------------------------------------------


class TestDictView:
    """``meta["k"]`` / ``dict(meta)`` / ``keys()`` 走最后一次出现的值."""

    def test_getitem_is_last_wins(self) -> None:
        assert _sample()["ti"] == "B"

    def test_getitem_missing(self) -> None:
        with pytest.raises(KeyError):
            _sample()["nope"]

    def test_get_default(self) -> None:
        assert _sample().get("nope", "d") == "d"
        assert _sample().get("ti") == "B"

    def test_keys_are_unique_and_ordered(self) -> None:
        assert list(_sample()) == ["ti", "ar"]

    def test_len_counts_distinct_keys(self) -> None:
        meta = _sample()
        assert len(meta) == 2
        assert len(meta.to_pairs()) == 3

    def test_dict_conversion_is_lossy(self) -> None:
        assert dict(_sample()) == {"ti": "B", "ar": "X"}
        assert _sample().to_dict() == {"ti": "B", "ar": "X"}

    def test_contains(self) -> None:
        meta = _sample()
        assert "ti" in meta
        assert "nope" not in meta

    def test_unhashable(self) -> None:
        """与 dict 一致: 可变容器不可哈希."""
        with pytest.raises(TypeError):
            hash(_sample())

    def test_values_view_follows_dict_view(self) -> None:
        assert sorted(_sample().values()) == ["B", "X"]


# ---------------------------------------------------------------------------
# 无损视角
# ---------------------------------------------------------------------------


class TestLosslessView:
    """``items()`` / ``to_pairs()`` / ``getlist()`` 给出全部条目."""

    def test_items_includes_duplicates(self) -> None:
        assert _sample().items() == DUPLICATED

    def test_to_pairs_returns_a_copy(self) -> None:
        meta = _sample()
        pairs = meta.to_pairs()
        pairs.append(("zz", "1"))
        assert meta.to_pairs() == DUPLICATED

    def test_getlist(self) -> None:
        meta = _sample()
        assert meta.getlist("ti") == ["A", "B"]
        assert meta.getlist("nope") == []


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------


class TestMutation:
    """``add`` 追加, ``set`` / ``[]=`` 替换, 以及 MutableMapping 的既有方法."""

    def test_add_appends(self) -> None:
        meta = Metadata({"ti": "A"})
        meta.add("ti", "B")
        assert meta.to_pairs() == [("ti", "A"), ("ti", "B")]

    def test_set_keeps_first_position(self) -> None:
        meta = Metadata([("ti", "A"), ("ar", "X"), ("ti", "B")])
        meta.set("ti", "C")
        assert meta.to_pairs() == [("ti", "C"), ("ar", "X")]

    def test_setitem_appends_when_absent(self) -> None:
        meta = Metadata({"ti": "A"})
        meta["ar"] = "X"
        assert meta.to_pairs() == [("ti", "A"), ("ar", "X")]

    def test_setitem_equals_set(self) -> None:
        left, right = _sample(), _sample()
        left["ti"] = "C"
        right.set("ti", "C")
        assert left == right

    def test_delitem_removes_every_occurrence(self) -> None:
        meta = _sample()
        del meta["ti"]
        assert meta.to_pairs() == [("ar", "X")]

    def test_delitem_missing(self) -> None:
        with pytest.raises(KeyError):
            del _sample()["nope"]

    def test_extend_from_metadata_keeps_duplicates(self) -> None:
        meta = Metadata()
        meta.extend(_sample())
        assert meta.to_pairs() == DUPLICATED

    def test_extend_from_dict(self) -> None:
        meta = Metadata()
        meta.extend({"a": "1", "b": "2"})
        assert meta.to_pairs() == [("a", "1"), ("b", "2")]

    def test_extend_from_pairs(self) -> None:
        meta = Metadata()
        meta.extend([("a", "1"), ("a", "2")])
        assert meta.getlist("a") == ["1", "2"]

    def test_update_is_dict_like(self) -> None:
        """``update`` 是覆盖语义 (与 dict 一致), 追加请用 ``extend``."""
        meta = Metadata([("a", "1")])
        meta.update({"a": "2", "b": "3"})
        assert meta.to_pairs() == [("a", "2"), ("b", "3")]

    def test_setdefault(self) -> None:
        meta = Metadata([("a", "1")])
        assert meta.setdefault("a", "9") == "1"
        assert meta.setdefault("b", "8") == "8"
        assert meta.to_pairs() == [("a", "1"), ("b", "8")]

    def test_pop_and_clear(self) -> None:
        meta = Metadata([("a", "1"), ("a", "2"), ("b", "3")])
        assert meta.pop("a") == "2"
        assert meta.to_pairs() == [("b", "3")]
        meta.clear()
        assert meta.to_pairs() == []

    def test_copy_is_independent(self) -> None:
        meta = _sample()
        clone = meta.copy()
        clone.add("mu", "Z")
        assert meta.getlist("mu") == []
        assert clone.getlist("mu") == ["Z"]


# ---------------------------------------------------------------------------
# 相等与展示
# ---------------------------------------------------------------------------


class TestEquality:
    """``Metadata`` 比全部条目, 其它 Mapping 比去重后的 dict 视角."""

    def test_metadata_equality_is_exact(self) -> None:
        assert _sample() == Metadata(DUPLICATED)
        assert _sample() != Metadata([("ar", "X"), ("ti", "B")])

    def test_metadata_equality_ignores_order_only_when_asked(self) -> None:
        assert Metadata([("a", "1"), ("b", "2")]) != Metadata([("b", "2"), ("a", "1")])

    def test_dict_equality_is_deduped(self) -> None:
        assert _sample() == {"ti": "B", "ar": "X"}

    def test_reflected_dict_equality(self) -> None:
        """``dict == meta`` 也要落到同一套规则上 (靠 Python 的反射比较).

        故意把 dict 写在左边: 这样走的是反射路径, 而不是 ``Metadata.__eq__``
        直接收到 dict. SIM300 的"改成 Yoda 顺序"会把这个用例测没, 所以保留.
        """
        assert {"ti": "B", "ar": "X"} == _sample()  # noqa: SIM300

    def test_not_equal_to_non_mapping(self) -> None:
        assert _sample() != 42
        assert _sample() != [("ti", "A")]

    def test_repr_without_duplicates(self) -> None:
        assert repr(Metadata({"ti": "A"})) == "Metadata({'ti': 'A'})"

    def test_repr_with_duplicates(self) -> None:
        assert repr(Metadata([("a", "1"), ("a", "2")])) == (
            "Metadata([('a', '1'), ('a', '2')])"
        )


# ---------------------------------------------------------------------------
# 与解析 / 序列化的接线
# ---------------------------------------------------------------------------


class TestParserIntegration:
    """解析器按 pair 累积, 序列化器按无损视角写出."""

    def test_duplicate_keys_across_lines_survive(self) -> None:
        lyrics = Lyrics.loads("[ti: A]\n[ar: X]\n[ti: B]\n[00:01.000]x\n")
        assert lyrics.metadata.getlist("ti") == ["A", "B"]
        assert lyrics.metadata["ti"] == "B"

    def test_duplicate_keys_on_one_line_survive(self) -> None:
        """同一行里的重复 key 也不能在这一层被折叠."""
        lyrics = Lyrics.loads("[ti: A][ti: B]\n[00:01.000]x\n")
        assert lyrics.metadata.getlist("ti") == ["A", "B"]

    def test_to_dict_is_lossy(self) -> None:
        lyrics = Lyrics.loads("[ti: A]\n[ti: B]\n[00:01.000]x\n")
        assert lyrics.to_dict()["metadata"] == {"ti": "B"}

    def test_dumps_writes_every_pair(self) -> None:
        lyrics = Lyrics.loads("[ti: A]\n[ti: B]\n[00:01.000]x\n")
        dumped = lyrics.dumps(options=SerializationOptions(line_separator="\n"))
        assert dumped == "[ti: A]\n[ti: B]\n[00:01.000]x\n"

    def test_duplicate_metadata_is_a_fixed_point(self) -> None:
        """写出再读回来仍是同样的条目 (改前这里会丢一个)."""
        text = "[ti: A]\n[ti: B]\n[00:01.000]x\n"
        options = SerializationOptions(line_separator="\n")
        once = Lyrics.loads(text).dumps(options=options)
        assert Lyrics.loads(once).metadata.to_pairs() == [("ti", "A"), ("ti", "B")]
        assert Lyrics.loads(once).dumps(options=options) == once

    def test_assignment_coerces_dict(self) -> None:
        """``lyrics.metadata = {...}`` 这种 0.4.x 写法仍然可用."""
        lyrics = Lyrics.loads("[00:01.000]x\n")
        lyrics.metadata = {"ti": "T"}
        assert isinstance(lyrics.metadata, Metadata)
        assert lyrics.metadata["ti"] == "T"

    def test_assignment_coerces_pairs(self) -> None:
        lyrics = Lyrics.loads("[00:01.000]x\n")
        lyrics.metadata = [("ti", "A"), ("ti", "B")]
        assert lyrics.metadata.getlist("ti") == ["A", "B"]

    @pytest.mark.parametrize("bad", ["ti", b"ti", 42])
    def test_assignment_rejects_non_mapping(self, bad: object) -> None:
        lyrics = Lyrics.loads("[00:01.000]x\n")
        with pytest.raises(ProgrammingError):
            lyrics.metadata = bad  # ty: ignore[invalid-assignment]

    def test_constructor_accepts_pairs(self) -> None:
        lyrics = Lyrics(metadata=[("ti", "A"), ("ti", "B")])
        assert lyrics.metadata.getlist("ti") == ["A", "B"]

    def test_slice_does_not_share_metadata(self) -> None:
        lyrics = Lyrics([], metadata={"ti": "T"})
        sliced = lyrics[:]
        sliced.metadata["ti"] = "改过的"
        assert lyrics.metadata["ti"] == "T"

    def test_copy_does_not_share_metadata(self) -> None:
        lyrics = Lyrics([], metadata=[("ti", "A"), ("ti", "B")])
        clone = lyrics.copy()
        clone.metadata.set("ti", "C")
        assert lyrics.metadata.getlist("ti") == ["A", "B"]

    def test_combine_self_wins(self) -> None:
        main = Lyrics([], metadata={"ti": "Main"})
        other = Lyrics([], metadata={"ti": "Other", "ar": "Artist"})
        combined = main.combine(other)
        assert combined.metadata.to_pairs() == [("ti", "Main"), ("ar", "Artist")]

    def test_combine_keeps_others_duplicates_for_missing_keys(self) -> None:
        """self 里没有的 key, other 的重复取值要全部搬过来."""
        main = Lyrics([], metadata={"ti": "Main"})
        other = Lyrics([], metadata=[("ar", "A"), ("ar", "B")])
        combined = main.combine(other)
        assert combined.metadata.getlist("ar") == ["A", "B"]
