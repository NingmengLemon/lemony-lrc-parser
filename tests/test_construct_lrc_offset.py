"""测试 construct_lrc 的 offset 相关逻辑.

覆盖 `positive_delays` 语义 (默认) :
    display_time = tag_time + offset
    正 offset → 歌词延后.
"""

from __future__ import annotations

from lemony_lrc_parser.models import OffsetSemantics, SerializationOptions
from lemony_lrc_parser.parser import parse_lrc as parse_file
from lemony_lrc_parser.serializer import dump_lrc as construct_lrc

_SAMPLE_LRC = """\
[ti: test]
[ar: someone]
[offset: 500]
[00:05.000]<00:05.000>hello<00:06.000>world<00:07.000>
[00:10.000]<00:10.000>second<00:11.500>line<00:12.000>
"""


class TestConstructLrcOffset:
    """针对 construct_lrc 中 offset 处理的测试."""

    def test_offset_not_applied_by_default(self) -> None:
        """默认 apply_offset_from_metadata=False 时不应用 offset, metadata.offset 保留原样."""
        ly = parse_file(_SAMPLE_LRC)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=False)
        )

        # offset 字段仍在
        assert "[offset: 500]" in out
        # 时间标签保持原样
        assert "[00:05.000]" in out
        assert "[00:10.000]" in out

    def test_positive_offset_applied(self) -> None:
        """offset=500 (positive_delays) 时, 所有时间标签应增加 500ms."""
        ly = parse_file(_SAMPLE_LRC)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        # offset 从 metadata 消失 (*_resolve_offset pop 掉了)
        assert "[offset:" not in out
        # 原 5000ms -> 5500ms (line.start)
        assert "[00:05.500]" in out
        # 原 10000ms -> 10500ms (line.start)
        assert "[00:10.500]" in out
        # 原 11500ms -> 12000ms (中间的 word tag, 保持尖括号)
        assert "<00:12.000>" in out
        # 原 7000ms -> 7500ms (行尾标签, 方括号)
        assert "[00:07.500]" in out
        # 原 12000ms -> 12500ms (line.end)
        assert "[00:12.500]" in out

    def test_negative_offset_applied(self) -> None:
        """负 offset 应让时间标签整体减小 (tag_time + (-2000) = tag_time - 2000)."""
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: -2000]")
        ly = parse_file(src)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        # 5000 + (-2000) = 3000
        assert "[00:03.000]" in out
        # 10000 + (-2000) = 8000
        assert "[00:08.000]" in out
        # metadata 被 pop 掉
        assert "[offset:" not in out

    def test_offset_too_large_triggers_partial_application(self) -> None:
        """
        负 offset 超过最小时间标签时, 只应用到最小时间标签的值, 剩余部分保留在 metadata.offset 中.

        原始最小时间 = 5000, offset = -6000 → min + (-6000) = -1000 → 越界
        → 只能应用 -5000 (使最小变为 0), 剩余 -1000 保留.
        """
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: -6000]")
        ly = parse_file(src)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        # 最小时间标签被 clamp 到 0 (line.start)
        assert "[00:00.000]" in out
        # 剩余 offset 应写回 metadata
        assert "[offset: -1000]" in out
        # 原 10000 + (-5000) = 5000 (line.start)
        assert "[00:05.000]" in out

    def test_offset_exactly_equal_to_min_time_but_negative(self) -> None:
        """offset 恰好等于 -min_time 时, 最小标签应变为 0, 不需要保留剩余 offset."""
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: -5000]")
        ly = parse_file(src)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        # 原 5000 + (-5000) = 0
        assert "[00:00.000]" in out
        # 原 10000 + (-5000) = 5000
        assert "[00:05.000]" in out
        # 不需要保留剩余 offset
        assert "[offset:" not in out

    def test_invalid_offset_is_ignored(self) -> None:
        """非整数的 offset 应被忽略, 不影响时间标签, 并且 offset 字段不再出现."""
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: not-a-number]")
        ly = parse_file(src)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        # 时间标签原样
        assert "[00:05.000]" in out
        assert "[00:10.000]" in out
        # offset 字段被 pop 掉了 (因为 apply_offset_from_metadata=True, 但内容无效)
        assert "[offset:" not in out

    def test_metadata_not_mutated_on_caller_side(self) -> None:
        """construct_lrc 不应修改上层传入的 Lyrics.metadata (因为内部拷贝了)."""
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: -6000]")
        ly = parse_file(src)
        before = dict(ly.metadata)
        _ = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )
        after = dict(ly.metadata)

        assert before == after, f"metadata 被污染了: before={before}, after={after}"
        assert ly.metadata.get("offset") == "-6000"

    def test_no_offset_in_metadata(self) -> None:
        """没有 offset 时, apply_offset_from_metadata=True 也应该正常工作."""
        src = _SAMPLE_LRC.replace("[offset: 500]\n", "")
        ly = parse_file(src)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        # 时间标签原样
        assert "[00:05.000]" in out
        assert "[00:10.000]" in out

    def test_roundtrip_equivalence(self) -> None:
        """
        应用 offset 后再 parse, 其时间应等价于原 lrc + 原 offset.

        即: 构造后的最小时间标签 + 剩余 offset == 原始最小时间标签 + 原始 offset.
        """
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: -6000]")
        ly = parse_file(src)
        out = construct_lrc(
            ly, options=SerializationOptions(apply_offset_from_metadata=True)
        )

        ly2 = parse_file(out)
        # 原始: 5000, offset=-6000 → 显示时间 = 5000 + (-6000) = -1000
        # 新的: line.start=0, offset=-1000 → 显示时间 = 0 + (-1000) = -1000 ✓
        new_first_start = ly2.lines[0].start
        new_offset = int(ly2.metadata.get("offset", "0"))
        assert new_first_start is not None
        assert new_first_start + new_offset == 5000 + (-6000)

    def test_positive_advances_semantics(self) -> None:
        """`positive_advances` 语义: 正 offset → 歌词提前 (tag_time - offset)."""
        ly = parse_file(_SAMPLE_LRC)
        out = construct_lrc(
            ly,
            options=SerializationOptions(
                apply_offset_from_metadata=True,
                offset_semantics=OffsetSemantics.positive_advances,
            ),
        )

        # offset 从 metadata 消失
        assert "[offset:" not in out
        # 原 5000ms - 500ms = 4500ms (line.start)
        assert "[00:04.500]" in out
        # 原 10000ms - 500ms = 9500ms (line.start)
        assert "[00:09.500]" in out
        # 原 7000ms - 500ms = 6500ms (行尾标签, 方括号)
        assert "[00:06.500]" in out
        # 原 12000ms - 500ms = 11500ms (line.end)
        assert "[00:11.500]" in out

    def test_positive_advances_negative_offset(self) -> None:
        """`positive_advances` + 负 offset: tag_time - (-2000) = tag_time + 2000."""
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: -2000]")
        ly = parse_file(src)
        out = construct_lrc(
            ly,
            options=SerializationOptions(
                apply_offset_from_metadata=True,
                offset_semantics=OffsetSemantics.positive_advances,
            ),
        )

        # 5000 - (-2000) = 7000
        assert "[00:07.000]" in out
        # 10000 - (-2000) = 12000
        assert "[00:12.000]" in out
        assert "[offset:" not in out

    def test_positive_advances_partial_application(self) -> None:
        """`positive_advances` + 正 offset 超过最小时间标签的裁剪.

        原始最小时间 = 5000, offset = 6000 → tag_time - 6000 → 越界
        → 只能应用 5000 (使最小变为 0), 剩余 1000 保留.
        """
        src = _SAMPLE_LRC.replace("[offset: 500]", "[offset: 6000]")
        ly = parse_file(src)
        out = construct_lrc(
            ly,
            options=SerializationOptions(
                apply_offset_from_metadata=True,
                offset_semantics=OffsetSemantics.positive_advances,
            ),
        )

        # 最小时间标签被 clamp 到 0
        assert "[00:00.000]" in out
        # 剩余 offset 应写回 metadata
        assert "[offset: 1000]" in out
        # 原 10000 - 5000 = 5000 (line.start)
        assert "[00:05.000]" in out
