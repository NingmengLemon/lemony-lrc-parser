"""汇总一份 LRC 语料的输入形态与解析结果.

用法::

    uv run python tools/corpus_stats.py <corpus-dir>

输出 Markdown 表格, 便于贴进 ``docs/research/``. 语料本身不进仓库.
"""

from __future__ import annotations

import argparse
import logging
import re
from collections import Counter
from pathlib import Path

from lemony_lrc_parser import Lyrics, parse_with_report

__all__ = ["main"]

TAG_ANY = re.compile(r"\[\d{1,4}:\d{1,2}")
TAG_ONLY = re.compile(r"^\s*\[\d{1,4}:\d{1,2}(?:[.:]\d{1,6})?\]\s*$")
METADATA = re.compile(r"^\s*\[([A-Za-z][A-Za-z0-9]{0,15}):")
MULTI_LEADING = re.compile(r"^\s*(?:\[\d{1,4}:\d{1,2}(?:[.:]\d{1,6})?\]){2,}")
FRACTION = re.compile(r"\[\d{1,4}:\d{1,2}[.:](\d{1,6})\]")
THREE_PART = re.compile(r"\[\d{1,4}:\d{1,2}:\d{1,2}\]")
TRUE_HOUR = re.compile(r"\[\d{1,3}:\d{1,2}:\d{1,2}\.\d{1,6}\]")
ANGLE = re.compile(r"<\d{1,4}:\d{1,2}")

CATEGORIES = ("original", "translated", "single")

#: 输出到 Markdown 表的指标, 按阅读顺序.
METRICS = (
    ("files", "文件"),
    ("lrc_files", "LRC 文件"),
    ("non_lrc_files", "无时间标签的文件"),
    ("lines", "行数"),
    ("byword_files", "含逐字标签的文件"),
    ("tag_only_lines", "只有时间标签的行"),
    ("blank_lines", "空行"),
    ("metadata_files", "含 metadata 的文件"),
    ("metadata_lines", "metadata 行"),
    ("digits_pure2", "行标签纯 2 位尾数"),
    ("digits_pure3", "行标签纯 3 位尾数"),
    ("digits_mixed", "行标签 2/3 位混用"),
    ("digits_none", "没有行标签尾数"),
    ("frac2", "2 位尾数标签"),
    ("frac3", "3 位尾数标签"),
    ("frac_other", "其它位数尾数标签"),
    ("mmss_cc_files", "含 [mm:ss:cc] 的文件"),
    ("true_hour_files", "含真小时标签的文件"),
    ("multi_leading_lines", "多行首标签行"),
    ("multi_leading_files", "含多行首标签的文件"),
    ("comment_lines", "注释行"),
    ("comment_files", "含注释行的文件"),
    ("offset_files", "含 [offset:] 的文件"),
    ("bom_files", "含 BOM 的文件"),
    ("crlf_files", "含 CRLF 的文件"),
    ("parse_errors", "解析异常"),
    ("validate_error_files", "validate error 文件"),
    ("roundtrip_mismatch_files", "行级往返不一致的文件"),
)


def category(name: str) -> str:
    if name.endswith(".original.lrc"):
        return "original"
    if name.endswith(".translated.lrc"):
        return "translated"
    return "single"


def line_view(lyrics: Lyrics) -> list[tuple[object, ...]]:
    return [
        (
            line.start,
            line.end,
            line.text,
            tuple(ref.text for ref in line.reference_lines),
        )
        for line in lyrics
    ]


def scan_file(path: Path) -> tuple[str, Counter[str], list[str], list[int]]:
    """返回 (类别, 计数, 报告事件代码, 主行 start 列表)."""
    cat = category(path.name)
    stats: Counter[str] = Counter()
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    stats["files"] = 1
    if raw.startswith(b"\xef\xbb\xbf"):
        stats["bom_files"] = 1
    if b"\r\n" in raw:
        stats["crlf_files"] = 1

    if not TAG_ANY.search(text):
        stats["non_lrc_files"] = 1
        return cat, stats, [], []

    stats["lrc_files"] = 1
    lines = text.splitlines()
    stats["lines"] = len(lines)

    if ANGLE.search(text):
        stats["byword_files"] = 1
    if "[offset:" in text.lower():
        stats["offset_files"] = 1

    n2 = n3 = other = 0
    for line in lines:
        if not line.strip():
            stats["blank_lines"] += 1
        if TAG_ONLY.match(line):
            stats["tag_only_lines"] += 1
        if METADATA.match(line):
            stats["metadata_lines"] += 1
            stats["metadata_files"] = 1
        if MULTI_LEADING.match(line):
            stats["multi_leading_lines"] += 1
            stats["multi_leading_files"] = 1
        if line.lstrip().startswith("#") or line.lstrip().startswith("[#"):
            stats["comment_lines"] += 1
            stats["comment_files"] = 1
        for match in FRACTION.finditer(line):
            digits = len(match.group(1))
            if digits == 2:
                n2 += 1
            elif digits == 3:
                n3 += 1
            else:
                other += 1

    stats["frac2"] = n2
    stats["frac3"] = n3
    stats["frac_other"] = other
    if n2 and n3:
        stats["digits_mixed"] = 1
    elif n2:
        stats["digits_pure2"] = 1
    elif n3:
        stats["digits_pure3"] = 1
    else:
        stats["digits_none"] = 1
    if THREE_PART.search(text):
        stats["mmss_cc_files"] = 1
    if TRUE_HOUR.search(text):
        stats["true_hour_files"] = 1

    try:
        lyrics, report = parse_with_report(text)
    except Exception:
        stats["parse_errors"] = 1
        return cat, stats, [], []

    if any(issue.severity == "error" for issue in lyrics.validate()):
        stats["validate_error_files"] = 1
    dumped = Lyrics.loads(lyrics.dumps())
    if line_view(lyrics) != line_view(dumped):
        stats["roundtrip_mismatch_files"] = 1

    return cat, stats, [event.code for event in report], [line.start for line in lyrics]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="包含 .lrc 文件的目录")
    args = parser.parse_args()

    logging.getLogger("lemony_lrc_parser").setLevel(logging.ERROR)

    files = sorted(path for path in args.corpus.iterdir() if path.is_file())
    stats = {cat: Counter() for cat in CATEGORIES}
    codes: Counter[str] = Counter()
    code_files: Counter[str] = Counter()
    starts: dict[str, dict[str, list[int]]] = {}

    for path in files:
        cat, file_stats, events, line_starts = scan_file(path)
        stats[cat].update(file_stats)
        for code in events:
            codes[code] += 1
        for code in set(events):
            code_files[code] += 1
        if cat in ("original", "translated"):
            base = path.name[: -len(f".{cat}.lrc")]
            starts.setdefault(base, {})[cat] = line_starts

    print("| 指标 | original | translated | single | 合计 |")
    print("| --- | --- | --- | --- | --- |")
    for key, label in METRICS:
        values = [stats[cat][key] for cat in CATEGORIES]
        print(f"| {label} | {values[0]} | {values[1]} | {values[2]} | {sum(values)} |")

    print()
    print("| 解析报告事件 | 次数 | 文件数 |")
    print("| --- | --- | --- |")
    for code, count in codes.most_common():
        print(f"| `{code}` | {count} | {code_files[code]} |")

    pairs = [
        pair for pair in starts.values() if "original" in pair and "translated" in pair
    ]
    exact = partial = zero = empty = 0
    for pair in pairs:
        original = set(pair["original"])
        translated = pair["translated"]
        if not translated:
            empty += 1
            continue
        hits = sum(1 for start in translated if start in original)
        if hits == len(translated):
            exact += 1
        elif hits:
            partial += 1
        else:
            zero += 1
    print()
    print("| 原文/译文配对 | 数值 |")
    print("| --- | --- |")
    print(f"| 配对数 | {len(pairs)} |")
    print(f"| 译文行时间戳全部对齐 | {exact} |")
    print(f"| 部分对齐 | {partial} |")
    print(f"| 完全对不上 | {zero} |")
    print(f"| 译文没有正文行 | {empty} |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
