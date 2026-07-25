"""命令行入口.

通过 ``python -m lemony_lrc_parser`` 使用. 优先支持的命令:

* ``validate`` —— 验证歌词数据一致性.
* ``offset``  —— 整体时间偏移.
* ``to-srt``  —— 转换为 SRT 字幕.
* ``to-webvtt`` —— 转换为 WebVTT 字幕.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exceptions import InvalidLyricsError, LyricsParserError
from .models import Lyrics, SerializationOptions
from .validation import ValidationOptions


def _resolve_args(args: list[str] | None = None) -> argparse.Namespace:
    """构建并解析命令行参数."""
    parser = argparse.ArgumentParser(
        prog="lemonyrics",
        description="LRC 歌词解析与处理工具.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- validate ----
    p_val = sub.add_parser("validate", help="验证 LRC 文件的数据一致性")
    p_val.add_argument("file", help="LRC 文件路径")
    p_val.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "遇到 error 级问题时以退出码 1 返回 (默认仅输出到 stderr). "
            "注意: 与 API 的 strict=True 不同, 此选项不会中止检查, "
            "所有问题仍会完整输出."
        ),
    )

    # ---- offset ----
    p_off = sub.add_parser("offset", help="对 LRC 文件整体时间偏移")
    p_off.add_argument("file", help="LRC 文件路径")
    p_off.add_argument(
        "--delta",
        type=int,
        required=True,
        help="偏移量 (毫秒), 正数→延后, 负数→提前",
    )
    p_off.add_argument(
        "-o", "--output", default=None, help="输出文件路径 (默认 stdout)"
    )

    # ---- to-srt ----
    p_srt = sub.add_parser("to-srt", help="转换为 SRT 字幕")
    p_srt.add_argument("file", help="LRC 文件路径")
    p_srt.add_argument(
        "-o", "--output", default=None, help="输出文件路径 (默认 stdout)"
    )

    # ---- to-webvtt ----
    p_vtt = sub.add_parser("to-webvtt", help="转换为 WebVTT 字幕")
    p_vtt.add_argument("file", help="LRC 文件路径")
    p_vtt.add_argument(
        "-o", "--output", default=None, help="输出文件路径 (默认 stdout)"
    )

    return parser.parse_args(args)


def _read_lrc(path: str) -> Lyrics:
    """从文件路径读取 LRC 并返回 Lyrics 对象."""
    try:
        return Lyrics.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"Error: failed to read {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    except (InvalidLyricsError, LyricsParserError) as exc:
        print(f"Error: failed to parse {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _write_output(text: str, output_path: str | None) -> bool:
    """将文本写到文件或 stdout, 返回写入是否成功."""
    if output_path:
        try:
            Path(output_path).write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"Error: failed to write {output_path}: {exc}", file=sys.stderr)
            return False
    else:
        sys.stdout.write(text)
    return True


def main(args: list[str] | None = None) -> int:
    """CLI 主入口, 返回退出码."""
    ns = _resolve_args(args)

    if ns.command == "validate":
        lyrics = _read_lrc(ns.file)
        issues = lyrics.validate(options=ValidationOptions(strict=False))
        if not issues:
            print(f"{ns.file}: OK (no issues)")
            return 0

        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        for w in warnings:
            loc = f"line {w.line_index}" if w.line_index is not None else "-"
            print(f"[WARNING] [{w.code}] {loc}: {w.message}", file=sys.stderr)

        for e in errors:
            loc = f"line {e.line_index}" if e.line_index is not None else "-"
            print(f"[ERROR] [{e.code}] {loc}: {e.message}", file=sys.stderr)

        return 1 if (ns.strict and errors) else 0

    elif ns.command == "offset":
        lyrics = _read_lrc(ns.file)
        try:
            shifted = lyrics.apply_delta(ns.delta)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        output = shifted.dumps(options=SerializationOptions())
        return 0 if _write_output(output, ns.output) else 1

    elif ns.command == "to-srt":
        lyrics = _read_lrc(ns.file)
        output = lyrics.to_srt()
        return 0 if _write_output(output, ns.output) else 1

    elif ns.command == "to-webvtt":
        lyrics = _read_lrc(ns.file)
        output = lyrics.to_webvtt()
        return 0 if _write_output(output, ns.output) else 1

    return 0
