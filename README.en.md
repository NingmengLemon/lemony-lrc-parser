# Lemony LRC Parser

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/lemony-lrc-parser)](https://pypi.org/project/lemony-lrc-parser/)

[简体中文](README.md) | **English**

Lemon-flavored LRC Parser for Python.

## Features

- Parse standard LRC lyric files
- Word-level lyric tags of Enhanced LRC / SPL
- Metadata tags
- Folded time tags
- Reference lines
- Lyrics merging
- Conversion to/from simple subtitle formats (SRT / WebVTT)
- Time offset (`apply_delta` / `<<` / `>>` operators)
- Dict serialization (`to_dict()` / `from_dict()`)
- Deep-copy method (`.copy()`)
- Configurable parse and serialization options
- Data consistency validation API (`validate_lyrics` / `Lyrics.validate()`)
- Text lookup (`contains_text()` / `find_text()`)
- Round-trip fidelity invariant tests (`parser output always validates` /
  `dumps converges in one round` / `line structure is stable`)
- CLI tool (`lemonyrics` / `python -m lemony_lrc_parser`)
- Parse errors carry the line number and raw line
  (`InvalidLyricsError.line_no` / `.raw_line`)
- Full type annotations

## Installation

It's recommended to use [uv](https://docs.astral.sh/uv/).

```bash
uv add lemony-lrc-parser
```

It's okay to use pip.

```bash
pip install lemony-lrc-parser
```

You can use the git repo as a source to catch the newest ~~bugs~~ features.

```bash
uv add https://github.com/NingmengLemon/lemony-lrc-parser.git
```

## Usage

### Quick Start

json, marshal or pickle -like usages

```python
import lemony_lrc_parser as llp

lrc_text = """[ti: Never Gonna Give You Up]
[ar: Rick Astley]

[00:18.68]We're no strangers to love
[00:22.65]You know the rules and so do I
[00:27.07]A full commitment's what I'm thinking of
[00:31.45]You wouldn't get this from any other guy
"""

# Parse
lyrics = llp.loads(lrc_text)

# Access metadata
print(lyrics.metadata["ti"])  # "Never Gonna Give You Up"
print(lyrics.metadata["ar"])  # "Rick Astley"

# Iterate over lyric lines
for line in lyrics:
    print(f"{line.start}ms: {line.text}")

# Serialize back to LRC format
output = llp.dumps(lyrics)
```

### OOP Interface

The `Lyrics` class provides an object-oriented entry point for parsing and
serialization, which is the recommended interface:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

# Lyrics is also a sequence container
print(len(lyrics))  # number of lines
print(lyrics[0].text)  # first line text
print(lyrics[-1].text)

# Slicing
first_three = lyrics[0:3]

# Serialize
lrc_output = lyrics.dumps()

# __str__ is equivalent to dumps()
print(lyrics)
```

### Word-level Lyrics

Parsing word-level (Enhanced LRC / SPL) lyrics:

```python
lrc_text = "[00:18.680]<00:18.810>We're<00:18.898> <00:19.077>no <00:19.248>strangers<00:19.768> <00:19.917>to <00:20.169>love[00:21.927]"

lyrics = llp.loads(lrc_text)
line = lyrics[0]

for word in line.content:
    print(f"  [{word.start} -> {word.end}] {word.content!r}")

# [18810 -> 18898] "We're"
# [18898 -> 19077] ' '
# [19077 -> 19248] 'no '
# [19248 -> 19768] 'strangers'
# [19768 -> 19917] ' '
# [19917 -> 20169] 'to '
# [20169 -> 21927] 'love'

# Line-level timing: line.start=18680, line.end=21927
# (the trailing [00:21.927] is taken as the line end time and written back
#  onto the last token's end)
```

### Search (contains_text / find_text)

Use the explicit methods for text lookup. `in` has different historical
semantics across the four models (`LyricToken` / `BasicLyricLine` are substring,
`LyricLine` is token equality, `Lyrics` is line equality), so `"xxx" in <model>`
keeps its old behavior but emits a `DeprecationWarning`:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

lyrics.contains_text("love")  # whether any line (incl. reference lines) contains the substring
matching = lyrics.find_text("love")  # list of matching line objects
line = lyrics[0]
line.contains_text("love")  # search the main line only
line.contains_text("爱", include_reference_lines=True)  # search reference lines too
```

Substring matching is case-sensitive; `casefold()` your inputs first if you need
case-insensitive comparison.

### Reference Lines (Translation / Transliteration)

In an LRC file, an untagged line immediately following a tagged line, or a line
that shares the same timestamp as the main line, is parsed as a reference line,
commonly used for translations or transliterations:

```python
lrc_text = """
[00:18.68]We're no strangers to love
[00:18.68]我们都是情场老手
"""

lyrics = llp.loads(lrc_text)

line = lyrics[0]
print(line.text)  # "We're no strangers to love"
print(line.reference_lines[0][0].content)  # "我们都是情场老手"
```

### Combining Lyrics

Merge two sets of lyrics (e.g. original and translation) by time tag:

```python
main = llp.loads("[00:01.00]Hello\n[00:02.00]World\n")
translation = llp.loads("[00:01.00]你好\n[00:02.00]世界\n")

# combine method: translation lines are attached to reference_lines at the same timestamp
combined = main.combine(translation)

# The + operator also works; note that + always uses other_as_refline_only=False,
# i.e. lines from the other side whose timestamps do not match are kept as new lines,
# not dropped
combined = main + translation

for line in combined:
    print(line.text)  # main lyrics
    for ref in line.reference_lines:
        ref_text = "".join(w.content for w in ref)
        print(f"  -> {ref_text}")  # reference lines

# With other_as_refline_only=False, lines in the translation without a matching timestamp are kept as new lines
combined = main.combine(translation, other_as_refline_only=False)
```

### Dict Serialization (to_dict / from_dict)

All data models support dict serialization, convenient for JSON transport and
API integration:

```python
import lemony_lrc_parser as llp
from lemony_lrc_parser import Lyrics

lyrics = llp.loads("[00:01.00]Hello\n[00:02.00]World\n")

# Lyrics → dict
data = lyrics.to_dict()
# {"metadata": {}, "lines": [{"start": 1000, ...}, ...]}

# dict → Lyrics
restored = Lyrics.from_dict(data)

# You can also operate on a single line, its content, or a single token
line = lyrics[0]
line_dict = line.to_dict()
token_dict = line.content[0].to_dict()
```

### Copy

All data models provide a `.copy()` deep-copy method returning an independent
copy:

```python
import lemony_lrc_parser as llp

lyrics = llp.loads("[00:01.00]Hello\n")

# Deep copy
clone = lyrics.copy()
clone.metadata["ti"] = "New Title"

# The original object is unaffected
print(lyrics.metadata.get("ti"))  # None
```

### Options

#### Parsing Options

```python
import re
from lemony_lrc_parser import Lyrics, ParseOptions

lrc_text = "[00:01.000]Hello\n[00:05.000]World\n"

lyrics = Lyrics.loads(
    lrc_text,
    options=ParseOptions(
        fill_implicit_line_end=True,  # whether to fill implicit line end times
        line_filter=r"纯音乐.*?请欣赏",  # blacklist filter (always treated as regex; str is auto-compiled)
        # line_filter=re.compile(r"纯音乐.*?请欣赏"),  # a precompiled regex is also accepted
    ),
)

# lyrics[0].end == lyrics[1].start == 5000
```

`line_filter` is a regular expression: a string is compiled with `re.compile`
and then matched against each line's text with `pattern.search`; matching lines
are dropped. For exact substring matching (rather than regex), wrap it with
`re.escape(...)`, e.g. `line_filter=re.escape("a.c")`.

Filtering is judged by the **main line** text only: reference lines (translation
/ transliteration) sharing the main line's timestamp are dropped together with
the main line, even if their own text does not match.

#### Serialization Options

Control serialization behavior via `SerializationOptions`:

```python
from lemony_lrc_parser import Lyrics, SerializationOptions

output = lyrics.dumps(
    options=SerializationOptions(
        with_metadata=True,  # whether to output the metadata section
        use_bracket_for_byword_tag=False,  # word tags use [...] or <...> (default; True does not guarantee round-trip, see below)
        line_tag_decimal_length=3,  # line tag millisecond digits (default 3)
        word_tag_decimal_length=3,  # word tag millisecond digits (default 3)
        line_separator="\n",  # inter-line separator (default "\n"; set to "" to omit blank lines)
    ),
)
```

#### Length of Decimal Part

With the defaults `line_tag_decimal_length=3` and `word_tag_decimal_length=3`,
output looks like `[00:01.000]` / `<00:01.050>`, preserving full millisecond
precision. If set to `2`, the decimal part represents centiseconds (e.g.
`[00:01.00]`), which is a **lossy truncation** (e.g. 555ms is truncated to 55 and
parses back as 550ms); weigh this as needed (some older software only supports
centiseconds).

#### Round-trip Fidelity

The output of `dumps()` should reconstruct the original object when re-parsed.
There are two known kinds of lossy write (see the table below): writes that are
the cost of the options themselves are written out anyway with a warning
(consistent with metadata handling), while writes LRC simply cannot express are
skipped with a debug log.

| Case | Text written | Result of re-parsing |
| --- | --- | --- |
| `use_bracket_for_byword_tag=True` and the first token is later than the line start | `[00:01.000][00:01.500]hello` | two lines, duplicated text |
| Reference line without text (its word timing is dropped too) | not written, debug log only | the reference line disappears |

`dumps` output is a fixed point "after at most one round": `d2 = dumps(loads(d1))`
and `d3 = dumps(loads(d2))` are guaranteed equal. Under the current
implementation (including 20k random corpora and 6622 real files) the first round
is already a fixed point.

Additionally, if a line end time was inferred from word tags and contradicts the
line start (`end <= start`), the inference is discarded (`line.end` set back to
`None`) with a warning — the parser never produces a line that `validate()` would
flag as an error.

### About SPL

[SPL (Salt Player Lyrics)](https://moriafly.com/standards/spl.html) is currently
the only document that codifies the compatibility problems the LRC family has hit
over the years, so this library uses it as the reference for LRC semantics. The
per-clause conformance cases live in
[`tests/test_spl_conformance.py`](tests/test_spl_conformance.py), and the corpus
statistics and research process are in
[`docs/research.md`](docs/research.md).

Where the parser follows SPL exactly:

- Timestamp number format (min 1-3 digits / sec 1-2 digits / ms 1-6 digits; fewer
  than 3 ms digits means trailing `0`s are omitted, i.e. `[00:01.5]` is 1.5s and
  `[00:01.02]` is 1.02s).
- Explicit line ends: `[start]text[end]` within a line, plus standalone end-marker
  lines `[end]`.
- An empty-text line is a "pure end marker": it produces no lyric line and does
  not participate in translation detection, only filling the previous line's `end`.
  So `[00:20.82]` + `[00:20.82]lyrics` yields "the previous line ends at 20.82s"
  plus "one normal lyric line", not "an empty line + its translation".
- Folded-line shorthand `[t1][t2]text`; same-timestamp translation detection (need
  not be adjacent) and the omitted-timestamp form (multiple lines).
- Both word-tag forms `[...]` and `<...>`, plus the "delayed first word"
  `[line tag]<first-word tag>text` added in the 2026-09-19 revision.
- Word tags must be increasing and fall within `[line start, line end]`;
  out-of-range or unordered tags are ignored (text on both sides is merged, no
  characters lost) with a warning.

Intentional deviations / areas the standard does not cover:

- 4-digit minutes (`[1234:00.000]`) are accepted more leniently than the standard;
  sec ≥ 60 is folded by literal value with a warning.
- When ms is written with 4-6 digits, it is truncated to milliseconds as the
  "fractional part of a second" (`[00:01.450000]` → 1450ms), rather than read as
  the literal 450000 ms per the standard. The standard is internally ambiguous
  about these two readings; 4-6 digits occur 0 times in the real corpus.
- Whitespace-only after a tag counts as text (see round-trip fidelity above); the
  standard only says "no text content follows".
- `[line tag][first-word tag]text` is read as a "delayed first word" single line
  when the whole line's tags are non-decreasing and the body still contains other
  time tags (e.g. `[00:05.650][00:05.730]徘[00:06.130]徊[00:06.450]`; the standard's
  "limitations" section reads it as a repeated line); `[t1][t2]text` with no other
  time tag in the body is still read as the folded repeated-line shorthand, i.e.
  two lines. In the real corpus, 199 lines use this form, 197 of which have
  the two tags only 0.1-1.3s apart.
- A line with only angle-bracket tags (e.g. `<00:01.000><00:02.000>`) is kept
  as an empty-text line to carry an empty subtitle cue; `dumps` writes it back
  in the same form.
- Implicit line ends are not filled by default (`end=None` means "unknown"); use
  `ParseOptions(fill_implicit_line_end=True)` for SPL's "lasts until the next line
  starts" semantics; subtitle export defaults to that semantics.

### Metadata Syntax

`[key: value]` counts as metadata only when the **whole line** consists of that
form: a `[key: value]` in the middle of body text does not swallow the line (e.g.
`Return [to: sender] now` is still a lyric or reference line).

Brackets inside a value must be **balanced**:

```python
import lemony_lrc_parser as llp

llp.loads("[al: Album [Deluxe]]\n[00:01.000]x\n").metadata
# {'al': 'Album [Deluxe]'}   ← preserved as-is (boundary = the matching ])
```

Unbalanced forms (e.g. `[ti: 50% ]off]`, `[ti: a [b]`) have no determinable value
boundary, so the whole line is treated as ordinary body text, and writing such a
value also warns.

Type hints for common keys are in `MetadataKey` / `MetadataDict` /
`COMMON_METADATA_KEYS` — these are hints only: the library does not restrict which
keys exist (the real corpus commonly contains `ly`, `mu`, `total`, `tool`), and
only `validate()` checks key format against `[A-Za-z][A-Za-z0-9]{0,15}`.

### Offset

Use `Lyrics.apply_delta(ms)` to apply a time offset; `ms` is *added directly* to
every tag's timestamp, which means passing a *positive* offset makes the lyrics
appear *later*, and vice versa.

You can also use the overloaded `>>` / `<<` operators to shift the lyrics.

If applying the offset would make any timestamp negative,
`TimestampUnderflowError` is raised for the caller to handle.

#### Applying Offset

Apply an offset to the timestamps via `Lyrics.apply_delta(ms)`, returning a new
object:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

# positive → lyrics appear later (equivalent to lyrics >> 500)
shifted = lyrics.apply_delta(500)

# negative → lyrics appear earlier (equivalent to lyrics << 500)
shifted = lyrics.apply_delta(-500)

# using the << / >> operators
shifted = lyrics >> 500  # later by 500ms
shifted = lyrics << 500  # earlier by 500ms

# shifted has offset timestamps; the original lyrics is unaffected
```

To offset timestamps before serializing, call `apply_delta()` first and serialize
the returned copy. If your offset comes from the lyric file metadata, you may also
need to manually clean up the offset value in `lyrics.metadata`.

#### Sign difference with LRC offset metadata

LRC has no standardized sign semantics, but:

- LRC's `[offset: +N]`, per community docs and mainstream implementations, means
  "shift the lyrics **earlier** by N ms", i.e. timestamp `-= N`
  ([research](docs/research.md));
- this library's `apply_delta(+ms)` is "timestamp `+= ms`", i.e. lyrics **later**.

So the correct way to apply an offset from metadata is to negate it:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads("[offset: 500]\n[00:10.000]hello\n")
shifted = lyrics.apply_delta(-int(lyrics.metadata["offset"]))
print(shifted[0].start)  # 9500 — earlier by 500ms
```

The library does **not** apply the offset automatically (explicit is better than
implicit); the caller has to handle it.

You can also quickly check the time range via `min_timestamp` / `max_timestamp`:

```python
from lemony_lrc_parser.offset import min_timestamp, max_timestamp

lyrics = Lyrics.loads(lrc_text)
print(min_timestamp(lyrics))  # minimum timestamp (ms), None if there are none
print(max_timestamp(lyrics))  # maximum timestamp (ms), None if there are none
```

### Validation

Use `lyrics.validate()` to check the data consistency of the lyrics:

```python
from lemony_lrc_parser import Lyrics, ValidationOptions

lyrics = Lyrics.loads(lrc_text)

# returns a list of issues
issues = lyrics.validate()
for issue in issues:
    print(f"[{issue.severity}] {issue.code}: {issue.message}")

# strict mode: raise InvalidLyricsError on error-level issues
issues = lyrics.validate(options=ValidationOptions(strict=True))
```

Checks include:

- whether lyric lines are sorted by time ascending (`unsorted`)
- whether duplicate timestamps exist (`duplicate-start`)
- whether a line end is later than its start (`end-not-after-start`)
- whether word token times are monotonically increasing (`token-nonmonotonic`)
- whether a word token's own interval is valid (`token-end-not-after-start`)
- whether a word token is within its line's time range (`token-before-line-start`
  / `token-after-line-end`)
- metadata key format validity (`invalid-metadata-key`)
- whether the `offset` metadata parses as an integer (`offset-not-int`)

Division of labor between `error` and `warning`: data written by the parser never
contains any `error`-level issue (see the invariant tests in
`tests/test_roundtrip_matrix.py`), so an `error` usually means the caller manually
constructed a self-contradictory object.

### CLI Usage

After installation, use it directly from the command line:

```bash
# validate LRC file data consistency
lemonyrics validate song.lrc
lemonyrics validate --strict song.lrc    # exit code 1 when there are errors

# global time offset (milliseconds)
lemonyrics offset --delta 500 song.lrc           # output to stdout
lemonyrics offset --delta -200 song.lrc -o out.lrc  # output to a file

# convert to subtitle formats
lemonyrics to-srt song.lrc
lemonyrics to-webvtt song.lrc -o song.vtt
```

You can also use `python -m lemony_lrc_parser` as the entry point.

### Subtitle Conversion (SRT / WebVTT)

`Lyrics` can convert to/from common simple subtitle formats, convenient for using
lyrics as video subtitles or importing existing subtitles as lyrics:

```python
from lemony_lrc_parser import Lyrics, SubtitleOptions

lyrics = Lyrics.loads("[00:01.000]Hello\n[00:03.000]World\n")

# LRC → SRT / WebVTT
srt_text = lyrics.to_srt()
vtt_text = lyrics.to_webvtt()

# SRT / WebVTT → LRC
lyrics2 = Lyrics.from_srt(srt_text)
lyrics3 = Lyrics.from_webvtt(vtt_text)

# top-level convenience functions also work
import lemony_lrc_parser as llp

srt_text = llp.dump_srt(lyrics)
vtt_text = llp.dump_webvtt(lyrics)
lyrics2 = llp.parse_srt(srt_text)
lyrics3 = llp.parse_webvtt(vtt_text)
```

Subtitles are keyed by `[start, end]` time intervals, which differs semantically
from LRC; conversion behavior is controlled via `SubtitleOptions`:

```python
options = SubtitleOptions(
    fill_end_from_next=True,  # when a line end is missing, fill from the next line's start
    default_duration_ms=5000,  # default duration when it can't be inferred (also used to fix invalid intervals)
    include_reference_lines=True,  # whether to output reference lines (translation/transliteration) as extra cue text
)

srt_text = lyrics.to_srt(options=options)
```

Conversion notes:

- LRC word tags and metadata are not written into subtitles (flattened/dropped).
- On export, if a line lacks `end`, it is filled from the next line's `start` or
  from `default_duration_ms` in turn; invalid intervals where `end <= start` are
  also fixed.
- A subtitle cue can contain multiple text lines: on export the main line comes
  first, reference lines after; on parse the first cue line is the main line and
  the rest are reference lines.
- Parsing automatically skips the WebVTT `WEBVTT` header and `NOTE` / `STYLE` /
  `REGION` blocks.

## References

- [CHANGELOG](CHANGELOG.md) — version history.
- Development notes ([index](docs/feature-ideas.md)):
  [roadmap](docs/roadmap.md) ·
  [design & trade-offs](docs/design.md) ·
  [risks & not-planned](docs/risks.md) ·
  [research & corpus data](docs/research.md)
- [LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_%28file_format%29)
- [SPL Specification](https://moriafly.com/standards/spl.html)

## UwU?

UwU!

## License

MIT License
