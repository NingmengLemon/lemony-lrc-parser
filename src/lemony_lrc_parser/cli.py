"""命令行入口.

通过 ``python -m lemony_lrc_parser`` 使用 (本库不注册 console script).
优先支持的命令:

* ``validate`` —— 报告解析时丢弃 / 忽略的内容, 并验证歌词数据一致性.
* ``offset``  —— 整体时间偏移.
* ``to-srt``  —— 转换为 SRT 字幕.
* ``to-webvtt`` —— 转换为 WebVTT 字幕.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .exceptions import LyricsParserError
from .models import Lyrics, SerializationOptions
from .parser import parse_with_report
from .report import STRICT_ERROR_CODES, ParseReport
from .validation import ValidationOptions

#: 库的根 logger; ``validate`` 期间在它上面挂 NullHandler, 见 :func:`_quiet_library_logs`.
_LIBRARY_LOGGER = "lemony_lrc_parser"


def _resolve_args(args: list[str] | None = None) -> argparse.Namespace:
    """构建并解析命令行参数."""
    parser = argparse.ArgumentParser(
        # 显式指定 prog: 走 ``python -m`` 时 sys.argv[0] 是 __main__.py 的完整
        # 路径, 交给 argparse 自行推断会让 usage 里出现 "__main__.py".
        prog="python -m lemony_lrc_parser",
        description="LRC 歌词解析与处理工具.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- validate ----
    p_val = sub.add_parser(
        "validate",
        help="报告解析时丢弃 / 忽略的内容, 并验证数据一致性",
        description=(
            "先报告解析过程中被丢弃或忽略的内容 (位置是源文件行号), 再报告解析结果的"
            "一致性问题 (位置是解析后的行下标). 默认只输出, 退出码为 0."
        ),
    )
    p_val.add_argument("file", help="LRC 文件路径")
    p_val.add_argument(
        "--fail-on-error",
        action="store_true",
        default=False,
        help=(
            "有 error 级问题时以退出码 1 返回. error 指一致性校验的 error, 以及"
            "严格模式下会被拒绝的解析事件 (丢弃了文件里的声明); 所有问题仍会"
            "完整输出."
        ),
    )
    # 0.4.x 的旧名. 它与 API 的 ParseOptions(strict=True) 同名却不同义 (那边是
    # 解析时当场抛异常), 所以改名; 0.5.x 里仍接受并提示, 0.6.0 移除.
    p_val.add_argument(
        "--strict",
        dest="deprecated_strict",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
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


def _read_text(path: str) -> str | None:
    """读取文件文本; 失败时打印错误并返回 ``None``.

    Note:
        这里刻意**不**调用 :func:`sys.exit`: 退出码统一由 :func:`main` 决定,
        这样 ``main()`` 的调用方 (含测试) 只需要看返回值, 不必同时处理
        "返回码"与 ``SystemExit`` 两套控制流.
    """
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
    except OSError as exc:
        print(f"Error: failed to read {path}: {exc}", file=sys.stderr)
    return None


def _read_lrc(path: str) -> Lyrics | None:
    """从文件路径读取并解析 LRC; 失败时打印错误并返回 ``None``."""
    text = _read_text(path)
    if text is None:
        return None
    try:
        return Lyrics.loads(text)
    except LyricsParserError as exc:
        print(f"Error: failed to parse {path}: {exc}", file=sys.stderr)
    return None


@contextmanager
def _quiet_library_logs() -> Iterator[None]:
    """临时屏蔽库自己的日志.

    ``validate`` 会把解析事件按结构化格式打印出来; 不屏蔽的话, 没配置 logging 时
    Python 的 last-resort handler 会把同一批 warning 再原样打一遍. 挂的是
    NullHandler 而不是改级别, 所以调用方自己配置的 handler (以及测试的 caplog)
    照常能收到.
    """
    logger = logging.getLogger(_LIBRARY_LOGGER)
    handler = logging.NullHandler()
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)


def _print_parse_report(report: ParseReport) -> int:
    """打印解析事件, 返回其中 error 级 (严格模式会拒绝的) 事件个数."""
    errors = 0
    for event in report:
        is_error = event.code in STRICT_ERROR_CODES
        errors += is_error
        level = "ERROR" if is_error else "WARNING"
        loc = f"line {event.line_no}" if event.line_no is not None else "-"
        print(f"[{level}] [{event.code}] {loc}: {event.message}", file=sys.stderr)
    return errors


def _validate(path: str, *, fail_on_error: bool) -> int:
    """``validate`` 子命令."""
    text = _read_text(path)
    if text is None:
        return 1
    try:
        with _quiet_library_logs():
            lyrics, report = parse_with_report(text)
    except LyricsParserError as exc:
        print(f"Error: failed to parse {path}: {exc}", file=sys.stderr)
        return 1

    parse_errors = _print_parse_report(report)
    issues = lyrics.validate(options=ValidationOptions(strict=False))
    # 先 warning 后 error, 让最要紧的留在终端最底部.
    ordered = sorted(issues, key=lambda issue: issue.severity == "error")
    for issue in ordered:
        level = issue.severity.upper()
        loc = f"lyrics[{issue.line_index}]" if issue.line_index is not None else "-"
        print(f"[{level}] [{issue.code}] {loc}: {issue.message}", file=sys.stderr)

    if not report and not issues:
        print(f"{path}: OK (no issues)")
        return 0
    errors = parse_errors + sum(issue.severity == "error" for issue in issues)
    return 1 if (fail_on_error and errors) else 0


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
        if ns.deprecated_strict:
            print(
                "Warning: --strict is deprecated and will be removed in 0.6.0; "
                "use --fail-on-error",
                file=sys.stderr,
            )
        return _validate(
            ns.file, fail_on_error=ns.fail_on_error or ns.deprecated_strict
        )

    elif ns.command == "offset":
        lyrics = _read_lrc(ns.file)
        if lyrics is None:
            return 1
        try:
            shifted = lyrics.apply_delta(ns.delta)
        # CLI 边界刻意宽捕获: 任何异常都转成 stderr 提示 + 退出码 1,
        # 不把 traceback 甩给终端用户.
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        output = shifted.dumps(options=SerializationOptions())
        return 0 if _write_output(output, ns.output) else 1

    elif ns.command == "to-srt":
        lyrics = _read_lrc(ns.file)
        if lyrics is None:
            return 1
        output = lyrics.to_srt()
        return 0 if _write_output(output, ns.output) else 1

    elif ns.command == "to-webvtt":
        lyrics = _read_lrc(ns.file)
        if lyrics is None:
            return 1
        output = lyrics.to_webvtt()
        return 0 if _write_output(output, ns.output) else 1

    return 0  # pragma: no cover - argparse required=True 保证命令必然匹配上面某支
