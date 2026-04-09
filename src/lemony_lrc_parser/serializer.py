from __future__ import annotations

from io import StringIO
from logging import getLogger

from .models import BasicLyricLine, Lyrics

logger = getLogger(__name__)


def ms2tag(ms: int, byword: bool = False, tail_digits: int = 3) -> str:
    mi = ms // 60000
    sec = (ms % 60000) // 1000
    ms = ms % 1000
    return (
        f"<{mi:02d}:{sec:02d}.{ms:0{tail_digits}d}>"
        if byword
        else f"[{mi:02d}:{sec:02d}.{ms:0{tail_digits}d}]"
    )


def construct_line(
    line: BasicLyricLine,
    use_bracket_for_byword_tag: bool = False,
    line_start: int | None = None,
    offset: int = 0,
) -> str:
    result = ""
    for idx, word in enumerate(line):
        prefix = ""
        suffix = (
            ""
            if word.end is None
            else ms2tag(word.end - offset, byword=not use_bracket_for_byword_tag)
        )
        if word.start is not None:
            if idx == 0:
                if word.start != line_start:
                    prefix = ms2tag(
                        word.start - offset,
                        byword=not use_bracket_for_byword_tag,
                    )
            elif line[idx - 1].end != word.start:
                prefix = ms2tag(
                    word.start - offset,
                    byword=not use_bracket_for_byword_tag,
                )
        result += f"{prefix}{word.content}{suffix}"

    return result


def _collect_all_times(lyrics: Lyrics) -> list[int]:
    """Collect all timestamps appearing in the lyrics (including line/word start/end, and reference lines)."""
    all_times: list[int] = []
    for line in lyrics.lines:
        if line.start is not None:
            all_times.append(line.start)
        if line.end is not None:
            all_times.append(line.end)
        for word in line.content:
            if word.start is not None:
                all_times.append(word.start)
            if word.end is not None:
                all_times.append(word.end)
        for refline in line.reference_lines:
            for word in refline:
                if word.start is not None:
                    all_times.append(word.start)
                if word.end is not None:
                    all_times.append(word.end)
    return all_times


def construct_lrc(
    lyrics: Lyrics,
    *,
    with_metadata: bool = True,
    use_bracket_for_byword_tag: bool = False,
    apply_offset_from_metadata: bool = False,
) -> str:
    buffer = StringIO()

    # Note: don't modify lyrics.metadata directly (would pollute caller's object), use a copy
    metadata = dict(lyrics.metadata)

    offset = 0
    if apply_offset_from_metadata and (offset_str := metadata.pop("offset", None)):
        try:
            offset = int(offset_str)
            logger.info(
                f"Applying global time offset: {offset}ms (from metadata.offset)"
            )
        except ValueError:
            logger.warning(
                f"Cannot parse metadata.offset as integer, ignoring this offset: {offset_str!r}"
            )
            offset = 0

    # Apply offset semantics (LRC specification):
    #   Positive offset makes lyrics display earlier, i.e., display_time = tag_time - offset
    # When offset > 0, some timestamps may become negative (especially the earliest one).
    # In this case, we only apply the "safe" part of offset (i.e., min_time), and keep
    # the remaining part in metadata.offset for the player to handle, ensuring all
    # timestamps in the generated LRC are >= 0.
    if offset > 0:
        all_times = _collect_all_times(lyrics)
        if all_times:
            min_time = min(all_times)
            if min_time - offset < 0:
                remaining_offset = offset - min_time
                logger.warning(
                    f"Applying offset={offset}ms would make minimum timestamp {min_time}ms negative, "
                    f"only applying {min_time}ms, remaining {remaining_offset}ms kept in metadata.offset"
                )
                offset = min_time
                # Write back even with with_metadata=False, as this is required for semantic correctness
                metadata["offset"] = str(remaining_offset)

    if with_metadata:
        for mk, mv in metadata.items():
            buffer.write(f"[{mk}: {mv}]\n")

    for line_idx, line in enumerate(lyrics.lines):
        if line_idx > 0:
            buffer.write("\n")
        line_start = line.start
        if line_start is None:
            logger.warning(f"Unknown line start time: {line}")
            continue
        buffer.write(ms2tag(line_start - offset))
        buffer.write(
            construct_line(
                line.content,
                use_bracket_for_byword_tag=use_bracket_for_byword_tag,
                line_start=line_start,
                offset=offset,
            )
        )
        if line.end is not None:
            buffer.write(ms2tag(line.end - offset))
        buffer.write("\n")

        for refline in line.reference_lines:
            buffer.write(ms2tag(line_start - offset))
            buffer.write(construct_line(refline, line_start=line_start, offset=offset))
            buffer.write("\n")

    return buffer.getvalue()
