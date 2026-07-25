"""测试 validation 模块."""

from __future__ import annotations

import pytest

from lemony_lrc_parser import (
    Lyrics,
    ValidationIssue,
    ValidationOptions,
    loads,
)
from lemony_lrc_parser.validation import validate_lyrics


def _assert_issue(
    issues: list[ValidationIssue],
    code: str,
    severity: str = "warning",
    line_index: int | None = None,
) -> ValidationIssue:
    """辅助: 从列表中找特定 code 的问题并校验 severity/line_index."""
    found = [i for i in issues if i.code == code]
    assert found, f"Expected issue with code={code!r}, got {[i.code for i in issues]}"
    issue = found[0]
    if severity:
        assert issue.severity == severity, f"code={code}: {issue!r}"
    if line_index is not None:
        assert issue.line_index == line_index, f"code={code}: {issue!r}"
    return issue


# ---------------------------------------------------------------------------
# 通过 Lyrics.validate() 间接测试
# ---------------------------------------------------------------------------


class TestValidateLyricsIntegration:
    """通过 Lyrics.validate() 测试验证能力."""

    def test_clean_lyrics_no_issues(self) -> None:
        """正常的歌词不应产生任何问题."""
        lrc = """[ti:test]
[00:01.000]hello
[00:03.000]world
"""
        lyrics = loads(lrc)
        issues = lyrics.validate()
        assert issues == []

    def test_clean_byword_no_issues(self) -> None:
        """正常逐字歌词不应产生问题."""
        lrc = """[00:01.000]<00:01.000>hello<00:02.000>world<00:03.000>
"""
        lyrics = loads(lrc)
        issues = lyrics.validate()
        assert issues == []

    def test_unsorted_lines(self) -> None:
        """乱序行应被检测 (运行最大值策略: 报告第一个乱序行)."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(start=5000, content=BasicLyricLine([LyricToken(content="b")]))
        )
        lyrics.append(
            LyricLine(start=1000, content=BasicLyricLine([LyricToken(content="a")]))
        )
        issues = lyrics.validate()
        _assert_issue(issues, "unsorted", severity="error", line_index=1)

    def test_multi_unsorted_lines(self) -> None:
        """多次乱序场景: [5000, 1000, 2000] 中 line 1 和 line 2 都应被检测."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(start=5000, content=BasicLyricLine([LyricToken(content="a")]))
        )
        lyrics.append(
            LyricLine(start=1000, content=BasicLyricLine([LyricToken(content="b")]))
        )
        lyrics.append(
            LyricLine(start=2000, content=BasicLyricLine([LyricToken(content="c")]))
        )
        issues = lyrics.validate()
        unsorted = [i for i in issues if i.code == "unsorted"]
        assert len(unsorted) >= 2, (
            f"Expected >= 2 unsorted issues, got {[i.line_index for i in unsorted]}"
        )
        assert {1, 2}.issubset({i.line_index for i in unsorted})

    def test_negative_timestamps_not_misflagged(self) -> None:
        """负时间戳行不应因 max_start 初始值问题被误判为乱序."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(start=-500, content=BasicLyricLine([LyricToken(content="a")]))
        )
        lyrics.append(
            LyricLine(start=-300, content=BasicLyricLine([LyricToken(content="b")]))
        )
        lyrics.append(
            LyricLine(start=0, content=BasicLyricLine([LyricToken(content="c")]))
        )
        issues = lyrics.validate()
        unsorted = [i for i in issues if i.code == "unsorted"]
        assert len(unsorted) == 0, (
            f"Negative timestamps incorrectly flagged as unsorted: {unsorted}"
        )

    def test_duplicate_starts(self) -> None:
        """重复 start 应被检测."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(start=1000, content=BasicLyricLine([LyricToken(content="a")]))
        )
        lyrics.append(
            LyricLine(start=1000, content=BasicLyricLine([LyricToken(content="b")]))
        )
        issues = lyrics.validate()
        _assert_issue(issues, "duplicate-start", severity="warning")

    def test_end_not_after_start(self) -> None:
        """end <= start 应被检测."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(
                start=1000,
                end=500,
                content=BasicLyricLine([LyricToken(content="bad")]),
            )
        )
        issues = lyrics.validate()
        _assert_issue(issues, "end-not-after-start", severity="error", line_index=0)

    def test_metadata_key_validation(self) -> None:
        """不合法 metadata key 应被检测."""
        # 解析器的 METATAG_REGEX 已经保证 key 以字母开头,
        # 因此通过手动注入非法 key 来测试验证逻辑.
        lyrics = loads("[00:01.000]hello\n")
        lyrics.metadata["1abc"] = "invalid"
        issues = lyrics.validate()
        _assert_issue(issues, "invalid-metadata-key", severity="warning")

    def test_offset_not_int(self) -> None:
        """offset 不可解析为整数时应被检测."""
        lrc = """[offset:abc]
[00:01.000]hello
"""
        lyrics = loads(lrc)
        issues = lyrics.validate()
        _assert_issue(issues, "offset-not-int", severity="warning")

    def test_offset_valid_int_no_issue(self) -> None:
        """offset 可解析为整数时不产生问题."""
        lrc = """[offset:500]
[00:01.000]hello
"""
        lyrics = loads(lrc)
        issues = lyrics.validate()
        assert not any(i.code == "offset-not-int" for i in issues)

    def test_empty_metadata_key(self) -> None:
        """metadata key 为空字符串时被检测."""
        lyrics = loads("[00:01.000]hello\n")
        lyrics.metadata[""] = "empty-key"
        issues = lyrics.validate()
        _assert_issue(issues, "invalid-metadata-key", severity="warning")

    def test_metadata_key_starts_with_digit(self) -> None:
        """metadata key 以数字开头时被检测."""
        lyrics = loads("[00:01.000]hello\n")
        lyrics.metadata["1bad"] = "starts-with-digit"
        issues = lyrics.validate()
        _assert_issue(issues, "invalid-metadata-key", severity="warning")

    def test_metadata_key_contains_special_chars(self) -> None:
        """metadata key 含特殊字符时被检测."""
        lyrics = loads("[00:01.000]hello\n")
        lyrics.metadata["bad-key"] = "has-hyphen"
        issues = lyrics.validate()
        _assert_issue(issues, "invalid-metadata-key", severity="warning")


# ---------------------------------------------------------------------------
# 直接测试 validate_lyrics 函数
# ---------------------------------------------------------------------------


class TestValidateLyricsDirect:
    """直接调用 validate_lyrics 测试底层能力."""

    def test_token_before_line_start(self) -> None:
        """token.start < line.start (B7)."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        line = LyricLine(
            start=2000,
            end=5000,
            content=BasicLyricLine(
                [
                    LyricToken(content="bad", start=1000, end=3000),
                ]
            ),
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        _assert_issue(
            issues, "token-before-line-start", severity="warning", line_index=0
        )

    def test_token_after_line_end(self) -> None:
        """token.end > line.end (B7)."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            end=3000,
            content=BasicLyricLine(
                [
                    LyricToken(content="bad", start=1000, end=5000),
                ]
            ),
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        _assert_issue(issues, "token-after-line-end", severity="warning", line_index=0)

    def test_token_end_not_after_start(self) -> None:
        """token.end <= token.start."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            end=5000,
            content=BasicLyricLine(
                [
                    LyricToken(content="bad", start=3000, end=2000),
                ]
            ),
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        _assert_issue(
            issues, "token-end-not-after-start", severity="error", line_index=0
        )

    def test_token_nonmonotonic(self) -> None:
        """token 时间不单调递增."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            end=5000,
            content=BasicLyricLine(
                [
                    LyricToken(content="a", start=1000, end=3000),
                    LyricToken(content="b", start=2000, end=4000),  # start < prev_end
                ]
            ),
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        _assert_issue(issues, "token-nonmonotonic", severity="error", line_index=0)

    def test_reference_line_checked_too(self) -> None:
        """参考行内部的 token 时间也检查单调性."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            content=BasicLyricLine([LyricToken(content="main")]),
            reference_lines=[
                BasicLyricLine(
                    [
                        LyricToken(content="a", start=3000, end=2000),
                    ]
                )
            ],
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        # 参考行内的 token-end-not-after-start 应被检测
        _assert_issue(
            issues, "token-end-not-after-start", severity="error", line_index=0
        )

    def test_empty_content_skipped(self) -> None:
        """空行内容不产生任何 token 检查结果."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            end=5000,
            content=BasicLyricLine([]),  # 空列表
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        # 没有任何 token 相关错误
        assert not any(
            i.code
            in (
                "token-end-not-after-start",
                "token-nonmonotonic",
                "token-before-line-start",
                "token-after-line-end",
            )
            for i in issues
        )

    def test_token_without_end_uses_start_as_prev(self) -> None:
        """token 缺少 end 时, prev_end 回退为 token.start (覆盖 L251)."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        line = LyricLine(
            start=1000,
            end=5000,
            content=BasicLyricLine(
                [
                    LyricToken(content="a", start=1000),  # 无 end
                    LyricToken(content="b", start=2000, end=3000),
                ]
            ),
        )
        lyrics.append(line)
        issues = validate_lyrics(lyrics)
        # 应无 token 级错误 (第二个 token 的 start=2000 >= 第一个 token 的 start=1000)
        assert not any(
            i.code in ("token-nonmonotonic", "token-end-not-after-start")
            for i in issues
        )


# ---------------------------------------------------------------------------
# strict mode
# ---------------------------------------------------------------------------


class TestValidateStrictMode:
    """测试 strict=True 时抛出异常."""

    def test_strict_mode_raises_on_error(self) -> None:
        """strict=True 且存在 error 级问题时抛出 InvalidLyricsError."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        import lemony_lrc_parser.exceptions as exc

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(
                start=5000,
                content=BasicLyricLine([LyricToken(content="b")]),
            )
        )
        lyrics.append(
            LyricLine(
                start=1000,
                content=BasicLyricLine([LyricToken(content="a")]),
            )
        )
        with pytest.raises(exc.InvalidLyricsError, match="unsorted"):
            lyrics.validate(options=ValidationOptions(strict=True))

    def test_strict_mode_warnings_do_not_raise(self) -> None:
        """strict=True 时只有 warning 不应抛异常."""
        lrc = """[offset:abc]
[00:01.000]hello
"""
        lyrics = loads(lrc)
        # offset-not-int 是 warning, 不应抛异常
        issues = lyrics.validate(options=ValidationOptions(strict=True))
        assert any(i.code == "offset-not-int" for i in issues)
