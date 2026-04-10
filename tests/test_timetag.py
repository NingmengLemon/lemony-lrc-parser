"""测试 timetag 模块的时间标签处理功能."""

from __future__ import annotations

import pytest

from lemony_lrc_parser.timetag import format_timetag, parse_timetag


class TestFormatTimetag:
    """测试 format_timetag 函数."""

    def test_basic_formatting(self) -> None:
        """测试基本的时间标签格式化."""
        # 基本格式
        assert format_timetag(0) == "[00:00.000]"
        assert format_timetag(5000) == "[00:05.000]"
        assert format_timetag(60000) == "[01:00.000]"
        assert format_timetag(61000) == "[01:01.000]"
        assert format_timetag(123456) == "[02:03.456]"

    def test_angle_bracket(self) -> None:
        """测试使用尖括号的逐字标签格式."""
        assert format_timetag(5000, use_angle_bracket=True) == "<00:05.000>"
        assert format_timetag(61000, use_angle_bracket=True) == "<01:01.000>"

    def test_tail_digits(self) -> None:
        """测试不同的毫秒位数."""
        assert format_timetag(5000, tail_digits=2) == "[00:05.00]"
        assert format_timetag(5000, tail_digits=1) == "[00:05.0]"
        assert format_timetag(123, tail_digits=3) == "[00:00.123]"

    def test_large_timestamp(self) -> None:
        """测试大时间戳."""
        # 超过1小时
        assert format_timetag(3600000) == "[60:00.000]"
        assert format_timetag(3661000) == "[61:01.000]"

    def test_negative_timestamp_raises(self) -> None:
        """测试负时间戳应该抛出 ValueError."""
        with pytest.raises(ValueError, match="Negative timestamp is not allowed"):
            format_timetag(-1)
        with pytest.raises(ValueError, match="Negative timestamp is not allowed"):
            format_timetag(-5000)


class TestParseTimetag:
    """测试 parse_timetag 函数."""

    def test_basic_parsing(self) -> None:
        """测试基本的时间标签解析."""
        assert parse_timetag("[00:00.000]") == 0
        assert parse_timetag("[00:05.000]") == 5000
        assert parse_timetag("[01:00.000]") == 60000
        assert parse_timetag("[01:01.000]") == 61000
        assert parse_timetag("[02:03.456]") == 123456

    def test_varied_milliseconds(self) -> None:
        """测试不同位数的毫秒."""
        # 1位毫秒
        assert parse_timetag("[00:00.1]") == 100
        # 2位毫秒
        assert parse_timetag("[00:00.12]") == 120
        # 3位毫秒
        assert parse_timetag("[00:00.123]") == 123

    def test_invalid_formats(self) -> None:
        """测试无效格式应该返回 None."""
        # 尖括号 (parse_timetag 只接受方括号)
        assert parse_timetag("<00:05.000>") is None
        # 缺少毫秒
        assert parse_timetag("[00:05]") is None
        # 缺少方括号
        assert parse_timetag("00:05.000") is None
        # 空字符串
        assert parse_timetag("") is None
        # 随机文本
        assert parse_timetag("not a timestamp") is None

    def test_edge_cases(self) -> None:
        """测试边界情况."""
        # 最大分钟数
        assert parse_timetag("[9999:59.999]") is not None
