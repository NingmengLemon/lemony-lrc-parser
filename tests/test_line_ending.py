"""行尾: 探测与写出.

两条规则:

* 写出的行尾只由 ``SerializationOptions.line_ending`` 决定, 与平台无关.
* 解析只探测、不沿用: 探测结果在 ``ParseReport.line_ending`` /
  :func:`detect_line_ending` 上, 要保留原文件风格得显式传回去.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lemony_lrc_parser import (
    Lyrics,
    ProgrammingError,
    SerializationOptions,
    detect_line_ending,
    dump_with_report,
    parse_with_report,
)
from lemony_lrc_parser.cli import main

CRLF_DOC = "[ti: T]\r\n[00:01.000]a\r\n翻译\r\n[00:02.000]b\r\n"


class TestDetect:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("a\nb\n", "lf"),
            ("a\r\nb\r\n", "crlf"),
            ("a\r\nb\n", "mixed"),
            ("a\rb\r", "mixed"),
            ("a\r\nb\r", "mixed"),
            ("no newline", None),
            ("", None),
        ],
    )
    def test_detect(self, text: str, expected: str | None) -> None:
        assert detect_line_ending(text) == expected

    def test_parse_report_carries_it(self) -> None:
        _, report = parse_with_report(CRLF_DOC)
        assert report.line_ending == "crlf"

    def test_it_is_not_an_event(self) -> None:
        """行尾描述源文本, 干净文件的报告仍然为空."""
        _, report = parse_with_report(CRLF_DOC)
        assert not report

    def test_parse_result_does_not_depend_on_line_ending(self) -> None:
        assert Lyrics.loads(CRLF_DOC) == Lyrics.loads(CRLF_DOC.replace("\r\n", "\n"))


class TestWrite:
    def test_default_is_lf_regardless_of_source(self) -> None:
        """解析时探测到的行尾不会自动沿用."""
        out = Lyrics.loads(CRLF_DOC).dumps()
        assert "\r" not in out

    def test_crlf(self) -> None:
        out = Lyrics.loads(CRLF_DOC).dumps(
            options=SerializationOptions(line_ending="crlf", line_separator="")
        )
        assert out == "[ti: T]\r\n[00:01.000]a\r\n[00:01.000]翻译\r\n[00:02.000]b\r\n"

    def test_explicit_pass_through(self) -> None:
        lyrics, report = parse_with_report(CRLF_DOC)
        assert report.line_ending in ("lf", "crlf")
        out = lyrics.dumps(
            options=SerializationOptions(
                line_ending=report.line_ending, line_separator=""
            )
        )
        assert detect_line_ending(out) == "crlf"

    def test_line_separator_follows_line_ending(self) -> None:
        """默认 ``line_separator="\\n"`` 的空行同样写成 CRLF."""
        out = Lyrics.loads(CRLF_DOC).dumps(
            options=SerializationOptions(line_ending="crlf")
        )
        assert "\r\n\r\n" in out
        assert detect_line_ending(out) == "crlf"

    def test_crlf_in_line_separator_is_not_doubled(self) -> None:
        out = Lyrics.loads(CRLF_DOC).dumps(
            options=SerializationOptions(line_ending="crlf", line_separator="\r\n")
        )
        assert "\r\r" not in out
        assert detect_line_ending(out) == "crlf"

    def test_dump_report_text_matches(self) -> None:
        options = SerializationOptions(line_ending="crlf")
        lyrics = Lyrics.loads(CRLF_DOC)
        assert dump_with_report(lyrics, options=options)[0] == lyrics.dumps(
            options=options
        )

    @pytest.mark.parametrize("value", ["auto", "cr", None, "CRLF"])
    def test_invalid_value(self, value: object) -> None:
        with pytest.raises(ProgrammingError, match="line_ending"):
            SerializationOptions(line_ending=value)  # ty: ignore[invalid-argument-type]


@given(
    st.lists(
        st.sampled_from(["[00:01.000]a", "b", "", "[ti: T]", "\u3000"]), max_size=8
    )
)
def test_crlf_output_reparses_identically(parts: list[str]) -> None:
    """CRLF 与 LF 写出的只是行尾不同: 换回 LF 就是同一个字符串, 读回来也相同."""
    lyrics = Lyrics.loads("\n".join(parts))
    lf = lyrics.dumps()
    crlf = lyrics.dumps(options=SerializationOptions(line_ending="crlf"))
    assert crlf.replace("\r\n", "\n") == lf
    assert "\r\r" not in crlf
    assert Lyrics.loads(crlf) == Lyrics.loads(lf)


class TestCli:
    """CLI 读写都不做换行转换, 所以字节级的行尾是确定的 (Windows 上也是)."""

    @pytest.fixture
    def crlf_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "in.lrc"
        path.write_bytes(CRLF_DOC.encode("utf-8"))
        return path

    @pytest.fixture
    def lf_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "in.lrc"
        path.write_bytes(CRLF_DOC.replace("\r\n", "\n").encode("utf-8"))
        return path

    @staticmethod
    def _offset(src: Path, out: Path, *extra: str) -> bytes:
        assert main(["offset", "--delta", "100", str(src), "-o", str(out), *extra]) == 0
        return out.read_bytes()

    def test_keep_crlf(self, crlf_file: Path, tmp_path: Path) -> None:
        data = self._offset(crlf_file, tmp_path / "out.lrc")
        assert data.count(b"\r\n") == data.count(b"\n") > 0
        assert b"\r\r" not in data

    def test_keep_lf(self, lf_file: Path, tmp_path: Path) -> None:
        assert b"\r" not in self._offset(lf_file, tmp_path / "out.lrc")

    def test_force_lf(self, crlf_file: Path, tmp_path: Path) -> None:
        data = self._offset(crlf_file, tmp_path / "out.lrc", "--line-ending", "lf")
        assert b"\r" not in data

    def test_force_crlf(self, lf_file: Path, tmp_path: Path) -> None:
        data = self._offset(lf_file, tmp_path / "out.lrc", "--line-ending", "crlf")
        assert data.count(b"\r\n") == data.count(b"\n") > 0

    def test_mixed_input_falls_back_to_lf(self, tmp_path: Path) -> None:
        src = tmp_path / "in.lrc"
        src.write_bytes(b"[00:01.000]a\r\n[00:02.000]b\n")
        assert b"\r" not in self._offset(src, tmp_path / "out.lrc")

    def test_stdout_without_buffer_falls_back_to_text(
        self, crlf_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stdout 被换成纯文本流 (没有 ``.buffer``) 时照常写文本."""
        import io

        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        assert main(["offset", "--delta", "0", str(crlf_file)]) == 0
        assert out.getvalue().count("\r\n") == out.getvalue().count("\n") > 0

    @pytest.mark.parametrize("command", [["offset", "--delta", "0"], ["to-srt"]])
    def test_parse_failure(
        self,
        command: list[str],
        crlf_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from lemony_lrc_parser import InvalidLyricsError

        def _fail(*args: object, **kwargs: object) -> object:
            raise InvalidLyricsError("boom")

        monkeypatch.setattr("lemony_lrc_parser.cli.Lyrics.loads", _fail)
        assert main([*command, str(crlf_file)]) == 1
        assert "failed to parse" in capsys.readouterr().err

    def test_stdout_is_not_translated(self, crlf_file: Path) -> None:
        """stdout 也按字节写: Windows 的文本模式不会把 CRLF 变成 ``\\r\\r\\n``."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "lemony_lrc_parser",
                "offset",
                "--delta",
                "0",
                str(crlf_file),
            ],
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.count(b"\r\n") == result.stdout.count(b"\n") > 0
        assert b"\r\r" not in result.stdout
