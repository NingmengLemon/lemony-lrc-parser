"""测试 merge 模块的精确/模糊匹配与合并报告."""

from __future__ import annotations

import pytest

from lemony_lrc_parser import (
    BasicLyricLine,
    LyricLine,
    Lyrics,
    LyricToken,
    MergeOptions,
    ProgrammingError,
    merge,
    merge_inplace,
    merge_with_report,
)


def _line(start: int, text: str, references: tuple[str, ...] = ()) -> LyricLine:
    return LyricLine(
        start=start,
        content=BasicLyricLine([LyricToken(content=text)]),
        reference_lines=[
            BasicLyricLine([LyricToken(content=reference)]) for reference in references
        ],
    )


def _texts(lyrics: Lyrics) -> list[str]:
    return [line.text for line in lyrics]


class TestExactMerge:
    def test_matched_lines_become_references(self) -> None:
        main = Lyrics([_line(1000, "A"), _line(2000, "B")])
        other = Lyrics([_line(1000, "甲"), _line(3000, "丙")])

        merged, report = merge_with_report(main, other)

        assert _texts(merged) == ["A", "B"]
        assert merged[0].reference_lines[0].text == "甲"
        assert report.exact_matches == 1
        assert report.fuzzy_matches == 0
        assert report.unmatched_main == (2000,)
        assert report.unmatched_other == (3000,)
        assert report.fuzzy_pairs == ()

    def test_unmatched_other_dropped_by_default(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(3000, "丙")])

        merged, report = merge_with_report(main, other)

        assert _texts(merged) == ["A"]
        assert report.unmatched_other == (3000,)

    def test_unmatched_other_kept_when_requested(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(3000, "丙")])

        merged, report = merge_with_report(
            main, other, options=MergeOptions(other_as_refline_only=False)
        )

        assert _texts(merged) == ["A", "丙"]
        assert merged[1].start == 3000
        assert report.unmatched_other == (3000,)

    def test_metadata_merges(self) -> None:
        main = Lyrics([_line(1000, "A")], metadata={"ti": "Main"})
        other = Lyrics([_line(1000, "甲")], metadata={"ti": "Other", "ar": "Artist"})

        merged = merge(main, other)

        assert merged.metadata.get("ti") == "Main"
        assert merged.metadata.get("ar") == "Artist"

    def test_inputs_are_not_mutated(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1000, "甲")])
        main_before, other_before = main.copy(), other.copy()

        merge(main, other)

        assert main == main_before
        assert other == other_before

    def test_combine_stays_exact(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1005, "甲")])

        assert _texts(main.combine(other)) == ["A"]

        merged = main.merge(other, options=MergeOptions(tolerance_ms=10))
        assert merged[0].reference_lines[0].text == "甲"

    def test_duplicate_main_starts_keep_all_lines(self) -> None:
        main = Lyrics([_line(1000, "A"), _line(1000, "B")])
        other = Lyrics([_line(1000, "甲")])

        merged = merge(main, other)

        assert _texts(merged) == ["A", "B"]
        assert merged[0].reference_lines[0].text == "甲"
        assert merged[1].reference_lines == []


class TestFuzzyMerge:
    def test_fuzzy_matches_with_tolerance(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1005, "甲")])

        merged, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )

        assert merged[0].reference_lines[0].text == "甲"
        assert report.exact_matches == 0
        assert report.fuzzy_matches == 1
        assert report.fuzzy_pairs == ((1000, 1005),)
        assert report.unmatched_other == ()

    def test_tolerance_is_inclusive(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1010, "甲")])

        _, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )
        assert report.fuzzy_matches == 1

        other = Lyrics([_line(1011, "乙")])
        _, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )
        assert report.fuzzy_matches == 0
        assert report.unmatched_other == (1011,)

    def test_zero_tolerance_is_exact(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1005, "甲")])

        _, report = merge_with_report(main, other)

        assert report.fuzzy_matches == 0
        assert report.unmatched_other == (1005,)

    def test_exact_match_wins_over_fuzzy(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1000, "甲"), _line(1005, "乙")])

        merged, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )

        assert [ref.text for ref in merged[0].reference_lines] == ["甲"]
        assert report.exact_matches == 1
        assert report.fuzzy_matches == 0
        assert report.unmatched_other == (1005,)

    def test_nearest_main_line_wins(self) -> None:
        main = Lyrics([_line(1000, "A"), _line(1100, "B")])
        other = Lyrics([_line(1095, "乙")])

        merged, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )

        assert merged[1].reference_lines[0].text == "乙"
        assert report.fuzzy_pairs == ((1100, 1095),)

    def test_each_main_line_matched_once(self) -> None:
        main = Lyrics([_line(1000, "A")])
        other = Lyrics([_line(1005, "甲"), _line(1006, "乙")])

        merged, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )

        assert [ref.text for ref in merged[0].reference_lines] == ["甲"]
        assert report.fuzzy_matches == 1
        assert report.unmatched_other == (1006,)

    def test_tie_prefers_earlier_main_line(self) -> None:
        main = Lyrics([_line(1000, "A"), _line(1010, "B")])
        other = Lyrics([_line(1005, "甲")])

        merged, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )

        assert merged[0].reference_lines[0].text == "甲"
        assert report.fuzzy_pairs == ((1000, 1005),)

    def test_unmatched_main_reported(self) -> None:
        main = Lyrics([_line(1000, "A"), _line(5000, "B")])
        other = Lyrics([_line(1000, "甲")])

        _, report = merge_with_report(main, other)

        assert report.unmatched_main == (5000,)

    def test_report_counts_add_up(self) -> None:
        main = Lyrics([_line(1000, "A"), _line(2000, "B")])
        other = Lyrics([_line(1000, "甲"), _line(2005, "乙"), _line(3000, "丙")])

        _, report = merge_with_report(
            main, other, options=MergeOptions(tolerance_ms=10)
        )

        assert report.exact_matches == 1
        assert report.fuzzy_matches == 1
        assert report.unmatched_other == (3000,)
        assert (
            report.exact_matches + report.fuzzy_matches + len(report.unmatched_other)
            == 3
        )


class TestInPlace:
    def test_merge_inplace_mutates_and_reports(self) -> None:
        main = Lyrics([_line(1000, "A")])

        report = merge_inplace(
            main, Lyrics([_line(1005, "甲")]), options=MergeOptions(tolerance_ms=10)
        )

        assert main[0].reference_lines[0].text == "甲"
        assert report.fuzzy_matches == 1

    def test_lyrics_merge_inplace_method(self) -> None:
        main = Lyrics([_line(1000, "A")])

        report = main.merge_inplace(Lyrics([_line(1000, "甲")]), options=MergeOptions())

        assert main[0].reference_lines[0].text == "甲"
        assert report.exact_matches == 1


class TestValidation:
    def test_negative_tolerance(self) -> None:
        with pytest.raises(ProgrammingError):
            MergeOptions(tolerance_ms=-1)

    def test_rejects_single_line(self) -> None:
        with pytest.raises(TypeError, match="LyricLine"):
            merge(
                Lyrics([_line(0, "A")]),
                _line(1000, "甲"),  # ty: ignore[invalid-argument-type]
            )

    def test_rejects_str(self) -> None:
        with pytest.raises(TypeError, match="str"):
            merge(
                Lyrics([_line(0, "A")]),
                "not lyrics",  # ty: ignore[invalid-argument-type]
            )

    def test_rejects_non_lyric_items(self) -> None:
        with pytest.raises(TypeError, match="LyricLine"):
            merge(
                Lyrics([_line(0, "A")]),
                [1, 2],  # ty: ignore[invalid-argument-type]
            )

    def test_rejects_non_iterable(self) -> None:
        with pytest.raises(TypeError, match="Iterable"):
            merge(
                Lyrics([_line(0, "A")]),
                1,  # ty: ignore[invalid-argument-type]
            )
