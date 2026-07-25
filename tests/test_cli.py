"""测试 CLI 命令行入口."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.cli import main

SAMPLE_LRC = """[ti:Test Song]
[ar:Test Artist]

[00:01.000]Hello
[00:03.000]World
"""


def _write_temp_lrc(content: str = SAMPLE_LRC) -> str:
    """写入临时文件并返回路径."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".lrc", encoding="utf-8", delete=False
    )
    tmp.write(content)
    tmp.close()
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
        """文件不存在时返回错误."""
        with pytest.raises(SystemExit) as exc_info:
            main(["validate", "/nonexistent/foo.lrc"])
        assert exc_info.value.code == 1

    def test_validate_bad_lrc(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """非法 LRC 文件应打印友好错误而非崩溃."""
        from lemony_lrc_parser.exceptions import InvalidLyricsError

        def _failing_loads(*args: object, **kwargs: object) -> object:
            raise InvalidLyricsError("test parse error")

        monkeypatch.setattr("lemony_lrc_parser.cli.Lyrics.loads", _failing_loads)
        path = _write_temp_lrc()
        try:
            with pytest.raises(SystemExit) as exc_info:
                main(["validate", path])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "failed to parse" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_strict_flag_accepted_clean(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--strict 标记在干净数据上不影响结果."""
        path = _write_temp_lrc()
        try:
            rc = main(["validate", "--strict", path])
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

    def test_os_error_during_read(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """读取文件时发生 OSError 应友好报错并退出."""

        def _failing_read_text(*args: object, **kwargs: object) -> object:
            raise OSError("permission denied")

        monkeypatch.setattr("pathlib.Path.read_text", _failing_read_text)
        path = _write_temp_lrc()
        try:
            with pytest.raises(SystemExit) as exc_info:
                main(["validate", path])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "failed to read" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_with_errors_no_strict_exit_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """有 error 但不带 --strict 时退出码仍为 0."""
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

        def _fake_loads(*args: object, **kwargs: object) -> Lyrics:
            return lyrics

        monkeypatch.setattr(Lyrics, "loads", _fake_loads)
        path = _write_temp_lrc()
        try:
            rc = main(["validate", path])
            captured = capsys.readouterr()
            # 不带 --strict, 有 error 但退出码仍为 0
            assert rc == 0
            assert "[ERROR]" in captured.err
            assert "unsorted" in captured.err
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_with_errors_strict_exit_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """有 error 且带 --strict 时退出码为 1."""
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

        def _fake_loads(*args: object, **kwargs: object) -> Lyrics:
            return lyrics

        monkeypatch.setattr(Lyrics, "loads", _fake_loads)
        path = _write_temp_lrc()
        try:
            rc = main(["validate", "--strict", path])
            captured = capsys.readouterr()
            assert rc == 1
            assert "[ERROR]" in captured.err
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
