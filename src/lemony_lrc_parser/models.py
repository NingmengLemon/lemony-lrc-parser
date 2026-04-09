from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NullableStartEndModel:
    start: int | None = None
    end: int | None = None


@dataclass
class StartEndModel:
    start: int
    end: int


@dataclass
class LyricWord(NullableStartEndModel):
    content: str = ""

    def __repr__(self) -> str:
        return (
            f"LyricWord(content={self.content!r}, start={self.start}, end={self.end})"
        )


BasicLyricLine = list[LyricWord]


@dataclass
class LyricLine(NullableStartEndModel):
    content: BasicLyricLine = field(default_factory=list)
    reference_lines: list[BasicLyricLine] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"LyricLine(start={self.start}, end={self.end}, content={self.content!r}, reference_lines={self.reference_lines!r})"


@dataclass
class Lyrics:
    lines: list[LyricLine] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Lyrics(lines={self.lines!r}, metadata={self.metadata!r})"

    def __add__(self, other: Any) -> Lyrics:
        if not isinstance(other, Lyrics):
            return NotImplemented
        return self.combine(other)

    def combine(self, other: Lyrics, *, other_as_refline_only: bool = True) -> Lyrics:
        new = Lyrics()
        new.metadata.update(other.metadata)
        new.metadata.update(self.metadata)

        pool: dict[int, LyricLine] = {}
        for line in self.lines:
            if line.start is None:
                continue
            pool[line.start] = line
        for line in other.lines:
            if line.start is None:
                continue
            if line.start in pool:
                pool[line.start].reference_lines.append(line.content)
                pool[line.start].reference_lines.extend(line.reference_lines)
            elif not other_as_refline_only:
                pool[line.start] = line
        new.lines = [deepcopy(v) for v in pool.values()]
        return new

    @classmethod
    def loads(cls, lrc: str) -> Lyrics:
        from lemony_lrc_parser.parser import parse_file

        return parse_file(lrc)

    def dumps(
        self, *, with_metadata: bool = True, use_bracket_for_byword_tag: bool = False
    ) -> str:
        from lemony_lrc_parser.serializer import construct_lrc

        return construct_lrc(
            self,
            with_metadata=with_metadata,
            use_bracket_for_byword_tag=use_bracket_for_byword_tag,
        )

    def __str__(self) -> str:
        return self.dumps()
