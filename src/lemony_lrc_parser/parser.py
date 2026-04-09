from __future__ import annotations

import re
from copy import deepcopy
from logging import getLogger

from .exceptions import LyricsParserError
from .models import BasicLyricLine, LyricLine, Lyrics, LyricWord
from .regex import (
    GENERIC_TIMETAG_REGEX,
    LINE_TIMETAG_REGEX,
    METATAG_REGEX,
    TIMETAG_REGEX_STRICT,
    compile_regex,
    is_match,
    is_str,
)

logger = getLogger(__name__)


def extract_time_from_match(match: re.Match[str]) -> int:
    """Extract milliseconds from a generic time tag match.

    Handles line_min/line_sec/line_tail or word_min/word_sec/word_tail named groups
    """
    groups = match.groupdict()

    # Try line time tag named groups
    min_val = groups.get("line_min") or groups.get("word_min")
    sec_val = groups.get("line_sec") or groups.get("word_sec")
    tail_val = groups.get("line_tail") or groups.get("word_tail")

    if min_val is None or sec_val is None:
        # Fallback to standard named groups (for LINE_TIMETAG_REGEX or WORD_TIMETAG_REGEX)
        min_val = groups.get("min", "0")
        sec_val = groups.get("sec", "0")
        tail_val = groups.get("tail")

    mi = int(min_val)
    sec = int(sec_val)

    if tail_val:
        # Normalize milliseconds to 3 digits
        if len(tail_val) > 3:  # Truncate
            tail_val = tail_val[:3]
        elif len(tail_val) < 3:  # Pad
            tail_val = tail_val.ljust(3, "0")
        ms = int(tail_val)
    else:
        ms = 0

    return int(ms + sec * 1000 + mi * 60 * 1000)


def validate_timetag_strict(s: str) -> None | int:
    ma = compile_regex(rf"^{TIMETAG_REGEX_STRICT}$").match(s)
    return match2ms(ma) if ma else None


def match2ms(match: re.Match[str]) -> int:
    """Extract milliseconds from standard named groups (min, sec, tail)."""
    match_dict = match.groupdict()
    mi = int(match_dict.get("min", "0"))
    sec = int(match_dict.get("sec", "0"))
    if tail := match_dict.get("tail"):
        # Normalize milliseconds to 3 digits
        if len(tail) > 3:  # Truncate
            tail = tail[:3]  # "123456" -> "123"
        elif len(tail) < 3:  # Pad
            tail = tail.ljust(3, "0")  # "1" -> "100", "12" -> "120"
        ms = int(tail)
    else:
        ms = 0
    return int(ms + sec * 1000 + mi * 60 * 1000)


def split_to_sequence(
    pattern: str | re.Pattern[str], text: str
) -> list[str | re.Match[str]]:
    if isinstance(pattern, str):
        pattern = compile_regex(pattern)
    result: list[str | re.Match[str]] = []
    last_index = 0

    for ma in pattern.finditer(text):
        # Between previous match end and current match start
        # If match.start() > last_index, there's plain text in between
        # Trick: including empty text ensures the sequence alternates: text-match-text
        result.append(text[last_index : ma.start()])

        result.append(ma)
        last_index = ma.end()

    # Handle text after the last match
    result.append(text[last_index:])
    # This ensures the sequence always starts and ends with text

    return result


def parse_line(line: str) -> BasicLyricLine | None:
    # Since folded lines are preprocessed upstream, we can treat all time tags equally
    if not line.strip():
        return None
    seq = split_to_sequence(
        GENERIC_TIMETAG_REGEX,
        line,
    )
    if not seq or (len(seq) == 1 and not seq[0]):
        return None

    if len(seq) % 2 != 1:
        raise LyricsParserError(
            f"Unexpected condition: sequence length should be odd, got: {len(seq)}"
        )

    # Unzip into two sequences:
    # text_seq: [0] [1] [2] [3] [4]
    #            | / | / | / | /
    # time_seq: [0] [1] [2] [3]
    text_seq: list[str] = []
    time_seq: list[int] = []
    for idx in range(len((seq))):
        if is_match(m := seq[idx]):
            # Use extract_time_from_match for generic time tag named groups
            time_seq.append(extract_time_from_match(m))
        elif is_str(s := seq[idx]):
            text_seq.append(s)
        else:
            raise LyricsParserError(
                f"Unexpected condition: sequence element should be str or Match, got {type(seq[idx])}"
            )

    # Special case
    if len(text_seq) == 1:
        if time_seq:
            raise LyricsParserError(
                f"Unexpected condition: when sequence length is 1, the only element should be str, got {type(seq[0])}"
            )
        return [LyricWord(content=text_seq[0])]

    if (d := (len(text_seq) - len(time_seq))) != 1:
        raise LyricsParserError(
            f"Unexpected condition: text sequence length minus time sequence length should be 1, got {d}"
        )

    offset = 0
    for idx in range(0, len(time_seq)):
        idx -= offset
        if idx > 0:
            now_time = time_seq[idx]
            prev_time = time_seq[idx - 1]
            if not (prev_time < now_time):
                logger.warning(
                    f"unordered time tag found: [prev={prev_time}, now={now_time}]"
                )
                text_seq[idx] += text_seq[idx + 1]
                text_seq.pop(idx + 1)
                time_seq.pop(idx)
                offset += 1

    result: BasicLyricLine = []
    for idx in range(0, len(text_seq)):
        word = LyricWord(content=text_seq[idx])
        if 0 < idx <= len(text_seq) - 1:
            word.start = time_seq[idx - 1]
        if 0 <= idx < len(text_seq) - 1:
            word.end = time_seq[idx]

        result.append(word)

    if len(result) < 2:
        raise LyricsParserError(
            f"Unexpected condition: preprocessed result sequence expected length >= 2, got {len(result)}"
        )

    # Remove empty head/tail so [0].start is line start and [-1].end is line end
    if not result[0].content:
        result.pop(0)
    if not result[-1].content and len(result) > 1:
        result.pop(-1)

    return result


def split_line_timetags(raw_line: str) -> tuple[list[re.Match[str]], str]:
    matches = []
    m = compile_regex(f"^{LINE_TIMETAG_REGEX}").match(raw_line)
    while m is not None:
        matches.append(m)
        raw_line = raw_line.removeprefix(m.group())
        m = compile_regex(f"^{LINE_TIMETAG_REGEX}").match(raw_line)
    return matches, raw_line


def extract_metadata(s: str) -> dict[str, str]:
    matches = [m.groupdict() for m in compile_regex(METATAG_REGEX).finditer(s)]
    return {m["key"]: m["value"] for m in matches}


def parse_file(lrc: str, *, fill_implicit_line_end: bool = False) -> Lyrics:
    metadata = {}
    line_pool: dict[int, LyricLine] = {}
    last_tag: int | None = None
    for raw_line in lrc.strip().splitlines():
        line_str = raw_line.strip()

        if m := extract_metadata(line_str):
            metadata.update(m)
            logger.debug(f"Metadata line, skipping lyric parsing: {line_str!r}")
            continue

        logger.debug(f"Parsing lyric line: {line_str!r}")
        matches, line_str = split_line_timetags(line_str)
        time_tags = [match2ms(m) for m in matches]
        line = parse_line(line_str)

        if not time_tags:
            if not line:
                last_tag = None
                logger.debug("Reference line marker reset")
                continue

            if last_tag is None:
                logger.warning(f"Orphaned lyric line: {line!r} (raw={raw_line!r})")
                continue

            logger.debug(
                f"Adding {line!r} as reference line for {line_pool[last_tag]!r}"
            )
            line_pool[last_tag].reference_lines.append(line)
            continue

        if not line:
            if (t := time_tags[0]) not in line_pool:
                line_pool[t] = LyricLine(start=t, content=[LyricWord(content="")])
            continue

        word_start = line[0].start
        for tag in time_tags:
            if word_start is not None and word_start < tag:
                logger.warning(
                    f"Invalid duplicate line time tag: {tag}ms, because it starts after first word ({word_start}ms)"
                )
                continue
            if tag in line_pool:
                # Multiple lyric lines at the same time point,
                # new one becomes reference line
                line_pool[tag].reference_lines.append(line)
            else:
                # Create a new LyricLine object instead of referencing the same line object
                # Need deep copy of line_content to avoid mutual influence
                line_pool[tag] = LyricLine(content=[deepcopy(word) for word in line])
        if len(time_tags) == 1:
            last_tag = time_tags[0]
        else:
            # Duplicate lines should not be reference for subsequent timestamp-less lines
            last_tag = None

    lyrics = Lyrics(metadata=metadata)
    sorted_lines = sorted(list(line_pool.items()), key=lambda o: o[0])
    for idx, (line_start, fline) in enumerate(sorted_lines):
        fline.start = line_start
        if (lw := fline.content[-1]).end is not None:
            fline.end, lw.end = lw.end, None

        # Optional feature: fill implicit line end
        if fill_implicit_line_end and fline.end is None and idx + 1 < len(sorted_lines):
            # Implicit end: continues until next line starts
            fline.end = sorted_lines[idx + 1][0]

        lyrics.lines.append(fline)

    return lyrics
