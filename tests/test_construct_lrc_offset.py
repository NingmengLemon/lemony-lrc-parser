"""测试 Lyrics.apply_delta 方法和偏移运算符.

语义统一为: 正数 → 歌词延后出现; 负数 → 歌词提前出现.
负偏移导致下溢时直接报错, 由用户自行处理.
"""

from __future__ import annotations

import pytest

from lemony_lrc_parser.exceptions import TimestampUnderflowError
from lemony_lrc_parser.parser import parse_lrc as parse_file
from lemony_lrc_parser.serializer import dump_lrc as construct_lrc

_SAMPLE_LRC = """\
[ti: test]
[ar: someone]
[offset: 500]
[00:05.000]<00:05.000>hello<00:06.000>world<00:07.000>
[00:10.000]<00:10.000>second<00:11.500>line<00:12.000>
"""


class TestApplyOffset:
    """针对 Lyrics.apply_delta 方法的测试."""

    def test_positive_offset_applied(self) -> None:
        """ms=500 时, 所有时间标签应增加 500ms."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = ly.apply_delta(500)
        out = construct_lrc(shifted)

        # 原 5000ms -> 5500ms (line.start), 默认 3 位小数 = 毫秒 500
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
        """负 ms 应让时间标签整体减小."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = ly.apply_delta(-2000)
        out = construct_lrc(shifted)

        # 5000 + (-2000) = 3000
        assert "[00:03.000]" in out
        # 10000 + (-2000) = 8000
        assert "[00:08.000]" in out

    def test_negative_offset_overflow_raises(self) -> None:
        """负偏移超过最小时间标签时应直接报错."""
        ly = parse_file(_SAMPLE_LRC)
        with pytest.raises(
            TimestampUnderflowError, match="would make minimum timestamp"
        ):
            ly.apply_delta(-6000)

    def test_offset_exactly_equal_to_min_time(self) -> None:
        """偏移恰好等于 -min_time 时, 最小标签应变为 0."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = ly.apply_delta(-5000)
        out = construct_lrc(shifted)

        # 原 5000 + (-5000) = 0
        assert "[00:00.000]" in out
        # 原 10000 + (-5000) = 5000
        assert "[00:05.000]" in out

    def test_original_not_mutated(self) -> None:
        """apply_delta 不应修改原始对象."""
        ly = parse_file(_SAMPLE_LRC)
        _ = ly.apply_delta(-2000)

        # 原始对象应保持不变
        assert ly.lines[0].start == 5000
        assert ly.metadata.get("offset") == "500"

    def test_zero_offset_returns_copy(self) -> None:
        """ms=0 时应返回深拷贝, 时间戳不变."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = ly.apply_delta(0)
        out = construct_lrc(shifted)

        # 时间标签原样
        assert "[00:05.000]" in out
        assert "[00:10.000]" in out
        # 是不同对象
        assert shifted is not ly

    def test_multiple_calls_independent(self) -> None:
        """多次调用 apply_delta 应各自返回新对象, 不影响原始对象."""
        ly = parse_file(_SAMPLE_LRC)
        _ = ly.apply_delta(100)
        _ = ly.apply_delta(200)
        _ = ly.apply_delta(300)
        # 原始对象始终不变
        assert ly.lines[0].start == 5000
        assert ly.metadata.get("offset") == "500"


class TestShiftOperators:
    """测试 ``<<`` / ``>>`` 运算符."""

    def test_rshift_positive_delays(self) -> None:
        """``>>`` 正数 → 歌词延后."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = ly >> 500
        out = construct_lrc(shifted)

        # 5500ms, 10500ms (默认 3 位小数)
        assert "[00:05.500]" in out
        assert "[00:10.500]" in out

    def test_lshift_positive_advances(self) -> None:
        """``<<`` 正数 → 歌词提前."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = ly << 2000
        out = construct_lrc(shifted)

        assert "[00:03.000]" in out
        assert "[00:08.000]" in out

    def test_lshift_overflow_raises(self) -> None:
        """``<<`` 导致下溢时应报错."""
        ly = parse_file(_SAMPLE_LRC)
        with pytest.raises(
            TimestampUnderflowError, match="would make minimum timestamp"
        ):
            _ = ly << 6000

    def test_operator_equivalence(self) -> None:
        """运算符与 apply_delta 语义一致."""
        ly = parse_file(_SAMPLE_LRC)

        assert (ly >> 500).dumps() == ly.apply_delta(500).dumps()
        assert (ly << 500).dumps() == ly.apply_delta(-500).dumps()

    def test_chained_shifts(self) -> None:
        """链式调用."""
        ly = parse_file(_SAMPLE_LRC)
        shifted = (ly >> 100) >> 200
        out = construct_lrc(shifted)

        # 5000 + 100 + 200 = 5300 → 毫秒 300
        assert "[00:05.300]" in out

    def test_original_unaffected_by_operators(self) -> None:
        """运算符不修改原始对象."""
        ly = parse_file(_SAMPLE_LRC)
        _ = ly >> 500
        _ = ly << 500

        assert ly.lines[0].start == 5000
