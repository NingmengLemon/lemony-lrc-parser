"""测试 CLI 命令行入口."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from lemony_lrc_parser import Lyrics, ParseReport
from lemony_lrc_parser.cli import main

SAMPLE_LRC = """[ti:Test Song]
[ar:Test Artist]

[00:01.000]Hello
[00:03.000]World
"""


def _write_temp_lrc(content: str = SAMPLE_LRC) -> str:
    """写入临时文件并返回路径."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lrc", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(content)
        return tmp.name


# ---------------------------------------------------------------------------


class TestCLIValidate:
    """测试 validate 命令."""

    def test_validate_clean(self, capsys: pytest.CaptureFixture[str]) -> None:
        """干净文件验证通过."""
        path = _write_temp_lrc()
        try:
            rc = main(["validate", path])
            captured = capsys.readouterr()
            assert rc == 0
            assert "OK" in captured.out
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_file_not_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        """文件不存在时返回退出码 1, 且不抛 SystemExit."""
        rc = main(["validate", "/nonexistent/foo.lrc"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "file not found" in captured.err

    def test_validate_bad_lrc(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """非法 LRC 文件应打印友好错误而非崩溃."""
        from lemony_lrc_parser.exceptions import InvalidLyricsError

        def _failing_loads(*args: object, **kwargs: object) -> object:
            raise InvalidLyricsError("test parse error")

        monkeypatch.setattr("lemony_lrc_parser.cli.parse_with_report", _failing_loads)
        path = _write_temp_lrc()
        try:
            rc = main(["validate", path])
            captured = capsys.readouterr()
            assert rc == 1
            assert "failed to parse" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_fail_on_error_accepted_clean(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--fail-on-error 在干净数据上不影响结果."""
        path = _write_temp_lrc()
        try:
            rc = main(["validate", "--fail-on-error", path])
            captured = capsys.readouterr()
            assert rc == 0
            assert "OK" in captured.out
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_with_warnings_ok(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """非 strict 模式下 warnings 不影响退出码."""
        bad = """[offset:abc]
[00:01.000]hello
"""
        path = _write_temp_lrc(bad)
        try:
            rc = main(["validate", path])
            captured = capsys.readouterr()
            assert rc == 0
            # 应输出 warning 信息到 stderr
            assert "offset-not-int" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_reports_parse_events_with_source_line_numbers(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """解析时丢掉 / 忽略的内容也要报, 位置是源文件行号."""
        path = tmp_path / "events.lrc"
        path.write_text("[00:01.000]a<00:00.500>b\n\norphan\n", encoding="utf-8")
        rc = main(["validate", str(path)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "OK" not in captured.out
        assert "[ERROR] [byword-before-line-start] line 1:" in captured.err
        assert "[ERROR] [orphaned-line] line 3:" in captured.err

    def test_validate_does_not_duplicate_library_logs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """事件只按结构化格式打一遍, 库的 warning 不再经 last-resort handler 重复输出."""
        path = tmp_path / "orphan.lrc"
        path.write_text("[00:01.000]a\n\norphan\n", encoding="utf-8")
        # 必须起子进程: pytest 的 logging 插件会在 root 上挂 handler, 进程内跑
        # main() 根本走不到 last-resort handler, 测不出重复输出.
        result = subprocess.run(
            [sys.executable, "-m", "lemony_lrc_parser", "validate", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        lines = result.stderr.splitlines()
        assert lines == [line for line in lines if line.startswith("[")], lines
        assert len(lines) == 1, lines

    def test_validate_keeps_caller_log_handlers(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """屏蔽的只是 last-resort 输出, 调用方自己的 handler 仍收得到日志."""
        path = tmp_path / "orphan.lrc"
        path.write_text("[00:01.000]a\n\norphan\n", encoding="utf-8")
        with caplog.at_level("WARNING", logger="lemony_lrc_parser"):
            main(["validate", str(path)])
        assert any("orphaned" in record.getMessage() for record in caplog.records)

    def test_parse_events_fail_with_fail_on_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """严格模式会拒绝的解析事件算 error, --fail-on-error 时退出码为 1."""
        path = tmp_path / "orphan.lrc"
        path.write_text("[00:01.000]a\n\norphan\n", encoding="utf-8")
        assert main(["validate", "--fail-on-error", str(path)]) == 1
        capsys.readouterr()

    def test_line_filtered_is_only_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """不在 STRICT_ERROR_CODES 里的事件按 warning 输出, 不影响退出码."""
        from lemony_lrc_parser.report import ParseEvent

        lyrics = Lyrics.loads("[00:01.000]a\n")
        report = ParseReport(events=(ParseEvent("line-filtered", "dropped"),))
        monkeypatch.setattr(
            "lemony_lrc_parser.cli.parse_with_report", lambda *a, **k: (lyrics, report)
        )
        path = _write_temp_lrc()
        try:
            rc = main(["validate", "--fail-on-error", path])
            captured = capsys.readouterr()
            assert rc == 0
            assert "[WARNING] [line-filtered] -: dropped" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_deprecated_strict_flag_still_works(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--strict 是 --fail-on-error 的旧名: 仍然生效, 但提示改名."""
        path = tmp_path / "orphan.lrc"
        path.write_text("[00:01.000]a\n\norphan\n", encoding="utf-8")
        rc = main(["validate", "--strict", str(path)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "--strict is deprecated" in captured.err
        assert "--fail-on-error" in captured.err


class TestCLIOffset:
    """测试 offset 命令."""

    def test_offset_positive(self, capsys: pytest.CaptureFixture[str]) -> None:
        """正数偏移."""
        path = _write_temp_lrc()
        try:
            rc = main(["offset", "--delta", "500", path])
            captured = capsys.readouterr()
            assert rc == 0
            # 偏移后时间应为 1500 和 3500
            assert "[00:01.500]" in captured.out
            assert "[00:03.500]" in captured.out
        finally:
            Path(path).unlink(missing_ok=True)

    def test_offset_negative(self, capsys: pytest.CaptureFixture[str]) -> None:
        """负数偏移."""
        path = _write_temp_lrc()
        try:
            rc = main(["offset", "--delta", "-500", path])
            captured = capsys.readouterr()
            assert rc == 0
            assert "[00:00.500]" in captured.out
        finally:
            Path(path).unlink(missing_ok=True)

    def test_offset_to_file(self) -> None:
        """偏移输出到文件."""
        path = _write_temp_lrc()
        out_path = path + ".out.lrc"
        try:
            rc = main(["offset", "--delta", "200", path, "-o", out_path])
            assert rc == 0
            out_text = Path(out_path).read_text(encoding="utf-8")
            assert "[00:01.200]" in out_text
        finally:
            Path(path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)

    def test_offset_underflow(self, capsys: pytest.CaptureFixture[str]) -> None:
        """负偏移过大导致下溢."""
        path = _write_temp_lrc()
        try:
            rc = main(["offset", "--delta", "-9999999", path])
            captured = capsys.readouterr()
            assert rc == 1
            assert "Error" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)


class TestCLIToSrt:
    """测试 to-srt 命令."""

    def test_to_srt_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """输出 SRT 到 stdout."""
        path = _write_temp_lrc()
        try:
            rc = main(["to-srt", path])
            captured = capsys.readouterr()
            assert rc == 0
            assert "00:00:01,000 -->" in captured.out
            assert "Hello" in captured.out
            assert "World" in captured.out
        finally:
            Path(path).unlink(missing_ok=True)

    def test_to_srt_to_file(self) -> None:
        """输出 SRT 到文件."""
        path = _write_temp_lrc()
        out_path = path + ".srt"
        try:
            rc = main(["to-srt", path, "-o", out_path])
            assert rc == 0
            srt_text = Path(out_path).read_text(encoding="utf-8")
            assert "00:00:01,000 -->" in srt_text
        finally:
            Path(path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)


class TestCLIToWebvtt:
    """测试 to-webvtt 命令."""

    def test_to_webvtt_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """输出 WebVTT 到 stdout."""
        path = _write_temp_lrc()
        try:
            rc = main(["to-webvtt", path])
            captured = capsys.readouterr()
            assert rc == 0
            assert captured.out.startswith("WEBVTT")
            assert "00:00:01.000 -->" in captured.out
        finally:
            Path(path).unlink(missing_ok=True)

    def test_to_webvtt_to_file(self) -> None:
        """输出 WebVTT 到文件."""
        path = _write_temp_lrc()
        out_path = path + ".vtt"
        try:
            rc = main(["to-webvtt", path, "-o", out_path])
            assert rc == 0
            vtt_text = Path(out_path).read_text(encoding="utf-8")
            assert vtt_text.startswith("WEBVTT")
        finally:
            Path(path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)


class TestCLIEdgeCases:
    """测试 CLI 边界情况."""

    @pytest.mark.parametrize(
        "argv",
        [["validate"], ["offset", "--delta", "500"], ["to-srt"], ["to-webvtt"]],
    )
    def test_read_failure_returns_one_for_every_command(
        self, argv: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """所有子命令在读取失败时都返回退出码 1 (统一由 main 决定, 不抛 SystemExit)."""
        rc = main([*argv, "/nonexistent/foo.lrc"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "file not found" in captured.err

    def test_os_error_during_read(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """读取文件时发生 OSError 应友好报错并返回退出码 1."""

        def _failing_read_text(*args: object, **kwargs: object) -> object:
            raise OSError("permission denied")

        monkeypatch.setattr("pathlib.Path.read_text", _failing_read_text)
        path = _write_temp_lrc()
        try:
            rc = main(["validate", path])
            captured = capsys.readouterr()
            assert rc == 1
            assert "failed to read" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_with_errors_no_strict_exit_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """有 error 但不带 --fail-on-error 时退出码仍为 0."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(
                start=5000,
                content=BasicLyricLine([LyricToken(content="b")]),
            )
        )
        lyrics.append(
            LyricLine(
                start=1000,
                content=BasicLyricLine([LyricToken(content="a")]),
            )
        )

        def _fake_parse(*args: object, **kwargs: object) -> tuple[Lyrics, ParseReport]:
            return lyrics, ParseReport()

        monkeypatch.setattr("lemony_lrc_parser.cli.parse_with_report", _fake_parse)
        path = _write_temp_lrc()
        try:
            rc = main(["validate", path])
            captured = capsys.readouterr()
            # 不带 --fail-on-error, 有 error 但退出码仍为 0
            assert rc == 0
            assert "[ERROR]" in captured.err
            assert "unsorted" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_with_errors_strict_exit_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """有 error 且带 --fail-on-error 时退出码为 1."""
        from lemony_lrc_parser.models import BasicLyricLine, LyricLine, LyricToken

        lyrics = Lyrics()
        lyrics.append(
            LyricLine(
                start=5000,
                content=BasicLyricLine([LyricToken(content="b")]),
            )
        )
        lyrics.append(
            LyricLine(
                start=1000,
                content=BasicLyricLine([LyricToken(content="a")]),
            )
        )

        def _fake_parse(*args: object, **kwargs: object) -> tuple[Lyrics, ParseReport]:
            return lyrics, ParseReport()

        monkeypatch.setattr("lemony_lrc_parser.cli.parse_with_report", _fake_parse)
        path = _write_temp_lrc()
        try:
            rc = main(["validate", "--fail-on-error", path])
            captured = capsys.readouterr()
            assert rc == 1
            assert "[ERROR]" in captured.err
            # 一致性问题的位置是解析后的行下标, 不是源文件行号
            assert "lyrics[1]" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_offset_exception_during_apply_delta(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """offset 命令在 apply_delta 抛异常时友好报错."""

        def _failing_apply_delta(*args: object, **kwargs: object) -> object:
            raise ValueError("simulated failure")

        monkeypatch.setattr(
            "lemony_lrc_parser.models.Lyrics.apply_delta", _failing_apply_delta
        )
        path = _write_temp_lrc()
        try:
            rc = main(["offset", "--delta", "100", path])
            captured = capsys.readouterr()
            assert rc == 1
            assert "Error" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.parametrize(
        "args",
        [
            ["offset", "--delta", "100"],
            ["to-srt"],
            ["to-webvtt"],
        ],
    )
    def test_write_output_os_error_returns_one(
        self,
        args: list[str],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """转换命令写入输出文件失败时应报错并返回退出码 1."""

        def _failing_write_text(*args: object, **kwargs: object) -> int:
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "write_text", _failing_write_text)
        path = _write_temp_lrc()
        try:
            rc = main([*args, path, "--output", "unwritable-output.lrc"])
            captured = capsys.readouterr()
            assert rc == 1
            assert "failed to write unwritable-output.lrc" in captured.err
            assert "permission denied" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_no_subcommand_shows_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """无子命令时 argparse 应报错."""
        with pytest.raises(SystemExit):
            main([])
        captured = capsys.readouterr()
        # argparse 会将用法打印到 stderr
        assert "usage:" in captured.err or "error:" in captured.err


class TestModuleEntryPoint:
    """``python -m lemony_lrc_parser`` 是本库唯一的 CLI 入口 (没有 console script).

    其余用例都直接调 :func:`main`, 覆盖不到 ``__main__.py`` 与 ``-m`` 的接线,
    而这条接线正是"去掉 console script"之后用户唯一的入口, 因此单独钉一个用例.
    """

    def test_dash_m_runs_the_cli(self) -> None:
        """``python -m`` 能跑通, 且 usage 里的 prog 不是 ``__main__.py``."""
        result = subprocess.run(
            [sys.executable, "-m", "lemony_lrc_parser", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert result.stdout.startswith("usage: python -m lemony_lrc_parser")
        assert "__main__.py" not in result.stdout

    def test_no_console_script_is_declared(self) -> None:
        """``pyproject.toml`` 里不应再声明 ``[project.scripts]``.

        用行首锚定的正则而不是子串判定, 免得注释里提一句就误报.
        """
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        assert re.search(r"^\[project\.scripts\]", text, re.MULTILINE) is None
