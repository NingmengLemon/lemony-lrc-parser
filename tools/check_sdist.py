"""检查 ``dist/`` 下的 sdist 是否混入了构建缓存 / 虚拟环境等无关内容.

背景: ``uv build --cache-dir .uv-cache`` 之类的用法会在仓库根留下缓存目录, 而
hatchling 的 sdist 默认会收录工作区里"未被 VCS 忽略"的所有内容 —— 曾经因此把
``.uv-cache/`` (427 个文件, 含 ``Scripts/python.exe``) 打进 sdist. 现在
``pyproject.toml`` 里已显式声明 ``[tool.hatch.build.targets.sdist] include``, 本
脚本作为回归防护在 CI 里跑一遍.

用法::

    uv build
    uv run python tools/check_sdist.py
"""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path

#: 出现在 sdist 路径中就说明打包范围失控的片段.
FORBIDDEN_PARTS: tuple[str, ...] = (
    "/.uv-cache/",
    "/.venv/",
    "/venv/",
    "/.tox/",
    "/htmlcov/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/.mypy_cache/",
    "/.ruff_cache/",
)

#: sdist 里必须存在的内容 (防止 include 列表把真正要发布的东西漏掉).
REQUIRED_PARTS: tuple[str, ...] = (
    "/src/lemony_lrc_parser/__init__.py",
    "/src/lemony_lrc_parser/py.typed",
    "/pyproject.toml",
    "/README.md",
    "/README.en.md",
    "/CHANGELOG.md",
    "/LICENSE",
)


def main(dist_dir: Path = Path("dist")) -> int:
    """检查 ``dist_dir`` 下的 sdist, 返回进程退出码."""
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if not sdists:
        print(f"no sdist found in {dist_dir}/; run `uv build` first", file=sys.stderr)
        return 1

    failed = False
    for sdist in sdists:
        with tarfile.open(sdist) as archive:
            names = archive.getnames()

        forbidden = sorted(
            {n for n in names if any(part in n for part in FORBIDDEN_PARTS)}
        )
        missing = sorted(
            {
                part
                for part in REQUIRED_PARTS
                if not any(n.endswith(part) for n in names)
            }
        )

        if forbidden:
            failed = True
            print(
                f"{sdist.name}: includes build artifacts / environments",
                file=sys.stderr,
            )
            for name in forbidden[:10]:
                print(f"  {name}", file=sys.stderr)
        if missing:
            failed = True
            print(f"{sdist.name}: missing required entries", file=sys.stderr)
            for part in missing:
                print(f"  {part}", file=sys.stderr)

        if not forbidden and not missing:
            print(f"{sdist.name}: {len(names)} entries, ok")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
