"""README 里带输出注释的示例必须真的产生那些输出.

按标题定位代码块, 执行它, 把 ``print`` 的输出与代码块里紧跟其后的 ``# ...`` 注释
比对. 中英两份 README 的示例是同一段代码, 两份都查, 免得一份改了另一份忘了.
要加别的示例, 往 :data:`SECTIONS` (还核对 ``Counter`` 那一行) 或
:data:`PRINT_ONLY_SECTIONS` (只核对 ``print`` 输出) 里追加即可.
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: (README 文件, 小节标题).
SECTIONS = [
    ("README.md", "#### 从看日志改成读报告"),
    ("README.en.md", "#### From reading logs to reading the report"),
]

#: 只核对 ``print`` 输出的小节.
PRINT_ONLY_SECTIONS = [
    ("README.md", "### 序列化报告"),
    ("README.en.md", "### Dump Report"),
]


def _code_block_after(text: str, heading: str) -> str:
    start = text.index(heading)
    match = re.compile(r"```python\n(.*?)```", re.S).search(text, start)
    assert match is not None, heading
    return match.group(1)


def _expected_prints(code: str) -> list[str]:
    """``for ... print(...)`` 之后的连续注释行就是期望输出."""
    lines = code.splitlines()
    last_print = max(i for i, line in enumerate(lines) if "print(" in line)
    expected = []
    for line in lines[last_print + 1 :]:
        if not line.startswith("# "):
            break
        expected.append(line[2:])
    return expected


@pytest.mark.parametrize(("readme", "heading"), SECTIONS)
def test_report_example_output(readme: str, heading: str) -> None:
    code = _code_block_after((ROOT / readme).read_text(encoding="utf-8"), heading)
    expected = _expected_prints(code)
    assert expected, "示例里应当写明期望输出"

    out = io.StringIO()
    namespace: dict[str, object] = {}
    # 示例会把库的 logger 调到 ERROR; 不还原的话, 后面靠 caplog 断言 warning 的
    # 用例会全部收不到日志.
    library_logger = logging.getLogger("lemony_lrc_parser")
    level = library_logger.level
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(code, f"{readme}:{heading}", "exec"), namespace)
    finally:
        library_logger.setLevel(level)
    assert out.getvalue().splitlines() == expected

    # Counter 那一行的注释同样要对得上
    counter = re.search(r"^Counter\(.*\)\n# (Counter\(.*\))$", code, re.M)
    assert counter is not None
    summary = eval(counter.group(0).splitlines()[0], namespace)
    assert repr(summary) == counter.group(1)


@pytest.mark.parametrize(("readme", "heading"), PRINT_ONLY_SECTIONS)
def test_print_examples(readme: str, heading: str) -> None:
    code = _code_block_after((ROOT / readme).read_text(encoding="utf-8"), heading)
    expected = _expected_prints(code)
    assert expected, "示例里应当写明期望输出"
    out = io.StringIO()
    library_logger = logging.getLogger("lemony_lrc_parser")
    level = library_logger.level
    library_logger.setLevel(logging.CRITICAL)  # 示例本身会触发 warning
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(code, f"{readme}:{heading}", "exec"), {})
    finally:
        library_logger.setLevel(level)
    assert out.getvalue().splitlines() == expected
