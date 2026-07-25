"""歌词数据一致性验证子系统.

提供结构化的 :class:`ValidationIssue` 与 :func:`validate_lyrics` 函数,
作为 strict mode、CLI validate、roundtrip 测试的共同地基.

本模块是独立子系统, 不依赖 :mod:`.parser` 或 :mod:`.serializer`,
仅消费 :mod:`.models` 的数据结构.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

from .models import BasicLyricLine, Lyrics

__all__ = [
    "ValidationIssue",
    "ValidationOptions",
    "ValidationSeverity",
    "validate_lyrics",
]

_DC_SLOTS: dict[str, bool] = (
    {"slots": True, "weakref_slot": True}
    if sys.version_info >= (3, 11)
    else {"slots": True}
    if sys.version_info >= (3, 10)
    else {}
)

ValidationSeverity = Literal["warning", "error"]


def _valid_metadata_key(key: str) -> bool:
    """检查一个 metadata key 是否符合当前 parser 支持的格式."""
    if not key:
        return False
    if not ("a" <= key[0] <= "z" or "A" <= key[0] <= "Z"):
        return False
    return all("a" <= c <= "z" or "A" <= c <= "Z" or "0" <= c <= "9" for c in key[1:])


@dataclass(frozen=True, **_DC_SLOTS)
class ValidationOptions:
    """验证选项.

    Attributes:
        strict: 若为 ``True``, 遇到 error 级别问题时通过
            :meth:`Lyrics.validate` 抛出 :class:`.exceptions.InvalidLyricsError`.
            默认 ``False``, 仅返回问题列表.
    """

    strict: bool = False


@dataclass(frozen=True, **_DC_SLOTS)
class ValidationIssue:
    """一条验证问题.

    Attributes:
        code: 问题代码 (如 ``"unsorted"``、``"token-oob"`` 等).
        message: 人类可读的描述信息.
        severity: ``"warning"`` 或 ``"error"``.
        line_index: 涉事行在 ``lyrics`` 中的下标 (从 0 开始), 未知时为 ``None``.
        token_index: 涉事词元在行内容中的下标, 未知时为 ``None``.
    """

    code: str
    message: str
    severity: ValidationSeverity = "warning"
    line_index: int | None = None
    token_index: int | None = None


def validate_lyrics(lyrics: Lyrics) -> list[ValidationIssue]:
    """验证一份 :class:`Lyrics` 的数据一致性, 返回问题列表.

    本函数是纯校验逻辑, 不包含 strict-mode 抛出异常的行为;
    后者由 :meth:`Lyrics.validate` 在上层处理.

    检查项:

    * 歌词行是否按 ``start`` 升序排列.
    * 是否存在重复 ``start``.
    * 是否存在 ``end is not None and end <= start``.
    * 逐字 token 的 ``start`` / ``end`` 是否单调递增.
    * 逐字 token 是否落在所属行的 ``[line.start, line.end]`` 范围内 (B7).
    * reference line 内部 token 的时间是否合理 (复用主行校验逻辑).
    * metadata key 是否符合当前 parser 支持的格式.
    * ``metadata.offset`` 是否可解析为整数.

    Args:
        lyrics: 待验证的歌词对象.
    """
    issues: list[ValidationIssue] = []

    _check_sort(lyrics, issues)
    _check_duplicate_starts(lyrics, issues)
    _check_line_end(lyrics, issues)
    _check_tokens(lyrics, issues)
    _check_metadata(lyrics, issues)

    return issues


# ---------------------------------------------------------------------------
# 各检查项实现
# ---------------------------------------------------------------------------


def _check_sort(lyrics: Lyrics, issues: list[ValidationIssue]) -> None:
    """检查行是否按 start 升序排列.

    使用运行最大值策略: 记录已扫描行中的最大 start, 若当前行 start
    小于该最大值, 则判定为乱序. 这比仅比较相邻行更稳健, 能正确检测
    多次乱序场景 (如 [5000, 1000, 2000] 中 line 2 也应报错).

    首行无条件接受 (包括负时间戳), 避免硬编码 ``max_start = -1``
    对理论上的负值场景误判.
    """
    max_start: int | None = None
    for i, line in enumerate(lyrics):
        if max_start is not None and line.start < max_start:
            issues.append(
                ValidationIssue(
                    code="unsorted",
                    message=f"Line {i} (start={line.start}ms) is out of order "
                    f"(expected >= {max_start}ms)",
                    severity="error",
                    line_index=i,
                )
            )
        else:
            max_start = line.start


def _check_duplicate_starts(lyrics: Lyrics, issues: list[ValidationIssue]) -> None:
    """检查是否存在重复 start."""
    seen: dict[int, int] = {}  # start -> first line_index
    for i, line in enumerate(lyrics):
        if line.start in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate-start",
                    message=f"Duplicate start={line.start}ms at lines "
                    f"{seen[line.start]} and {i}",
                    severity="warning",
                    line_index=i,
                )
            )
        else:
            seen[line.start] = i


def _check_line_end(lyrics: Lyrics, issues: list[ValidationIssue]) -> None:
    """检查 end <= start 的情况."""
    for i, line in enumerate(lyrics):
        if line.end is not None and line.end <= line.start:
            issues.append(
                ValidationIssue(
                    code="end-not-after-start",
                    message=f"Line {i}: end={line.end}ms <= start={line.start}ms",
                    severity="error",
                    line_index=i,
                )
            )


def _check_tokens(lyrics: Lyrics, issues: list[ValidationIssue]) -> None:
    """检查每行及其参考行的 token 一致性."""
    for line_idx, line in enumerate(lyrics):
        _check_line_tokens(
            line.content,
            line.start,
            line.end,
            label=f"Line {line_idx}",
            line_idx=line_idx,
            issues=issues,
        )
        for ref_idx, refline in enumerate(line.reference_lines):
            _check_line_tokens(
                refline,
                line.start,
                None,
                label=f"Line {line_idx} ref {ref_idx}",
                line_idx=line_idx,
                issues=issues,
                is_reference=True,
            )


def _check_line_tokens(
    content: BasicLyricLine,
    line_start: int,
    line_end: int | None,
    *,
    label: str,
    line_idx: int,
    issues: list[ValidationIssue],
    is_reference: bool = False,
) -> None:
    """检查单行 (或参考行) 内容中 token 的时间一致性.

    对主行:
    - token 的 start/end 必须单调递增.
    - token 的 start >= line_start (B7).
    - token 的 end <= line_end (当 line_end 存在时) (B7).
    - token 自身 end > start (当两者都存在时).

    对参考行: 只检查 token 自身的单调性和内部一致性.
    """
    if len(content) == 0:
        return

    prev_end: int | None = None
    for tok_idx, token in enumerate(content):
        # ---- 检查内部一致性 (end > start) ----
        if token.start is not None and token.end is not None:
            if token.end <= token.start:
                issues.append(
                    ValidationIssue(
                        code="token-end-not-after-start",
                        message=f"{label} token {tok_idx}: "
                        f"end={token.end}ms <= start={token.start}ms",
                        severity="error",
                        line_index=line_idx,
                        token_index=tok_idx,
                    )
                )

        # ---- 检查单调性 ----
        if prev_end is not None and token.start is not None:
            if token.start < prev_end:
                issues.append(
                    ValidationIssue(
                        code="token-nonmonotonic",
                        message=f"{label} token {tok_idx}: "
                        f"start={token.start}ms < prev_end={prev_end}ms",
                        severity="error",
                        line_index=line_idx,
                        token_index=tok_idx,
                    )
                )

        # 更新 prev_end (优先用 token.end, 其次 token.start)
        if token.end is not None:
            prev_end = token.end
        elif token.start is not None:
            prev_end = token.start

        # ---- 对主行检查越界 (B7) ----
        if is_reference:
            continue

        if token.start is not None and token.start < line_start:
            issues.append(
                ValidationIssue(
                    code="token-before-line-start",
                    message=f"{label} token {tok_idx}: "
                    f"start={token.start}ms < line.start={line_start}ms",
                    severity="warning",
                    line_index=line_idx,
                    token_index=tok_idx,
                )
            )

        if token.end is not None and line_end is not None and token.end > line_end:
            issues.append(
                ValidationIssue(
                    code="token-after-line-end",
                    message=f"{label} token {tok_idx}: "
                    f"end={token.end}ms > line.end={line_end}ms",
                    severity="warning",
                    line_index=line_idx,
                    token_index=tok_idx,
                )
            )


def _check_metadata(lyrics: Lyrics, issues: list[ValidationIssue]) -> None:
    """检查 metadata key 合法性与 offset 可解析性."""
    for key in lyrics.metadata:
        if not _valid_metadata_key(key):
            issues.append(
                ValidationIssue(
                    code="invalid-metadata-key",
                    message=f"Metadata key {key!r} does not match expected pattern "
                    "(alpha-numeric, starting with letter)",
                    severity="warning",
                )
            )

    offset_raw = lyrics.metadata.get("offset")
    if offset_raw is not None:
        try:
            int(offset_raw)
        except ValueError:
            issues.append(
                ValidationIssue(
                    code="offset-not-int",
                    message=f"metadata.offset value {offset_raw!r} is not a valid integer",
                    severity="warning",
                )
            )
