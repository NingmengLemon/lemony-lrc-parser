"""歌词合并.

精确匹配按行首 ``start``; 可选毫秒级容差做模糊匹配. 每次合并都可以产出一份
:class:`MergeReport`, 记录精确匹配、模糊匹配与未匹配的行.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .exceptions import ProgrammingError
from .models import LyricLine, Lyrics

__all__ = [
    "MergeOptions",
    "MergeReport",
    "merge",
    "merge_inplace",
    "merge_with_report",
]


@dataclass(frozen=True)
class MergeOptions:
    """合并策略.

    Attributes:
        other_as_refline_only: 若为 ``True`` (默认), ``other`` 中找不到对应时间点
            的行会被丢弃; 若为 ``False``, 这些行会保留为新行.
        tolerance_ms: 模糊匹配的容差 (毫秒), 默认 0 即只做精确匹配. 几毫秒的
            时间轴偏差可以传 10 一类的值; 容差越大越容易把不相关的行挂在一起.
    """

    other_as_refline_only: bool = True
    tolerance_ms: int = 0

    def __post_init__(self) -> None:
        if self.tolerance_ms < 0:
            raise ProgrammingError(
                f"tolerance_ms must be non-negative, got {self.tolerance_ms}"
            )


@dataclass(frozen=True)
class MergeReport:
    """一次合并的可审计结果.

    Attributes:
        exact_matches: 按 ``start`` 精确匹配到的 ``other`` 行数.
        fuzzy_matches: 按容差模糊匹配到的 ``other`` 行数.
        unmatched_main: 没有被匹配的主行 ``start``, 按主行顺序. 同一 ``start``
            有多行时, 未匹配的后行会让同一个 ``start`` 重复出现.
        unmatched_other: 没有被匹配的 ``other`` 行 ``start``, 按 ``other`` 行顺序.
        fuzzy_pairs: 模糊匹配的 ``(主行 start, other 行 start)``, 按处理顺序.
    """

    exact_matches: int
    fuzzy_matches: int
    unmatched_main: tuple[int, ...]
    unmatched_other: tuple[int, ...]
    fuzzy_pairs: tuple[tuple[int, int], ...] = ()


def merge(
    main: Lyrics,
    other: Lyrics | Iterable[LyricLine],
    *,
    options: MergeOptions | None = None,
) -> Lyrics:
    """将 ``other`` 合并进 ``main``, 返回新实例; 语义见 :func:`merge_inplace`."""
    new = main.copy()
    merge_inplace(new, other, options=options)
    return new


def merge_with_report(
    main: Lyrics,
    other: Lyrics | Iterable[LyricLine],
    *,
    options: MergeOptions | None = None,
) -> tuple[Lyrics, MergeReport]:
    """同 :func:`merge`, 同时返回 :class:`MergeReport`."""
    new = main.copy()
    report = merge_inplace(new, other, options=options)
    return new, report


def merge_inplace(
    main: Lyrics,
    other: Lyrics | Iterable[LyricLine],
    *,
    options: MergeOptions | None = None,
) -> MergeReport:
    """将 ``other`` 原地合并进 ``main``, 返回报告.

    匹配顺序:

    1. 先按 ``start`` 精确匹配; 命中多个 ``other`` 行时全部挂到同一主行.
    2. 剩下的 ``other`` 行在未匹配的主行里找 ``abs(delta) <= tolerance_ms``
       的最近一行; 每个主行最多被模糊匹配一次, 距离相同取更早的主行.
    3. 仍未匹配的 ``other`` 行按 ``other_as_refline_only`` 丢弃或保留为新行;
       保留时, 同一 ``start`` 的后续行挂到第一条新行上, 与旧的合并行为一致.

    Args:
        main: 主歌词; 会被修改.
        other: 另一份歌词或 ``LyricLine`` 可迭代对象.
        options: 合并策略; ``None`` 使用 :class:`MergeOptions` 的默认值.

    Returns:
        本次合并的报告.

    Raises:
        TypeError: ``other`` 不是 :class:`Lyrics` 或 ``LyricLine`` 可迭代对象.
        ProgrammingError: ``options.tolerance_ms < 0``.
    """
    opts = options if options is not None else MergeOptions()
    other_lines = _coerce_other(other)

    # metadata 以 main 为准, other 作为补充. 按 key 判存在与否, 把 other 的
    # 全部同名取值都搬过来, 不折叠重复项.
    if isinstance(other, Lyrics):
        for key in other.metadata:
            if key not in main.metadata:
                for value in other.metadata.getlist(key):
                    main.metadata.add(key, value)

    # main 中同一 start 可能存在多行 (手工构造 / from_srt 等来源), 全部保留;
    # exact 匹配挂到该时间点首次出现的主行上, 与解析器对重复时间戳的语义一致.
    main_lines = list(main)
    anchor_index: dict[int, int] = {}
    for index, line in enumerate(main_lines):
        anchor_index.setdefault(line.start, index)

    matched_main: set[int] = set()
    pending_other: list[LyricLine] = []
    exact_matches = 0

    for line in other_lines:
        index = anchor_index.get(line.start)
        if index is None:
            pending_other.append(line)
            continue
        anchor = main_lines[index]
        _attach_reference(anchor, line)
        matched_main.add(index)
        exact_matches += 1

    fuzzy_matches = 0
    unmatched_other: list[int] = []
    fuzzy_pairs: list[tuple[int, int]] = []
    appended: dict[int, LyricLine] = {}

    for line in pending_other:
        appended_anchor = appended.get(line.start)
        if appended_anchor is not None:
            _attach_reference(appended_anchor, line)
            unmatched_other.append(line.start)
            continue
        best: tuple[int, int, int] | None = None
        for index, anchor in enumerate(main_lines):
            if index in matched_main:
                continue
            delta = abs(anchor.start - line.start)
            if delta > opts.tolerance_ms:
                continue
            candidate = (delta, anchor.start, index)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            unmatched_other.append(line.start)
            if not opts.other_as_refline_only:
                new_line = line.copy()
                appended[line.start] = new_line
                main.data.append(new_line)
            continue
        _, _, index = best
        anchor = main_lines[index]
        _attach_reference(anchor, line)
        matched_main.add(index)
        fuzzy_matches += 1
        fuzzy_pairs.append((anchor.start, line.start))

    # 稳定排序: main 内同 start 的多行保持原有相对顺序.
    main.data.sort(key=lambda line: line.start)

    return MergeReport(
        exact_matches=exact_matches,
        fuzzy_matches=fuzzy_matches,
        unmatched_main=tuple(
            line.start
            for index, line in enumerate(main_lines)
            if index not in matched_main
        ),
        unmatched_other=tuple(unmatched_other),
        fuzzy_pairs=tuple(fuzzy_pairs),
    )


def _attach_reference(anchor: LyricLine, line: LyricLine) -> None:
    """把 ``line`` 的正文与参考行挂到 ``anchor`` 上, 不共享对象."""
    anchor.reference_lines.append(line.content.copy())
    anchor.reference_lines.extend(ref.copy() for ref in line.reference_lines)


def _coerce_other(other: Lyrics | Iterable[LyricLine]) -> list[LyricLine]:
    """校验并展开合并对象."""
    if isinstance(other, LyricLine):
        raise TypeError(
            "expected Lyrics or an iterable of LyricLine, not a single "
            "LyricLine (did you mean [lyric_line]?)"
        )
    if isinstance(other, str):
        raise TypeError("expected Lyrics or an iterable of LyricLine, not str")
    if not isinstance(other, Iterable):
        raise TypeError("Lyrics or Iterable[LyricLine] is expected")
    raw_items = list(other)
    other_lines = [item for item in raw_items if isinstance(item, LyricLine)]
    if raw_items and not other_lines:
        kinds = sorted({type(item).__name__ for item in raw_items})
        raise TypeError(
            "expected an iterable of LyricLine; "
            f"got {len(raw_items)} item(s) of type {kinds}"
        )
    return other_lines
