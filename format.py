# /// script
# requires-python = ">=3.13"
# dependencies = ["yapf==0.43.0"]
# ///
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


FORMAT_ROOTS = (
    "dmdcontrol",
    "tests",
    "compat",
    "debug_scripts",
    "hannah_cam_code",
)

EXCLUDED_PARTS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root_name in FORMAT_ROOTS:
        root = Path(root_name)
        if not root.exists():
            continue
        files.extend(
            path for path in root.rglob("*.py")
            if not any(part in EXCLUDED_PARTS for part in path.parts)
        )
    return sorted(files)


def main() -> int:
    files = _python_files()
    for path in files:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "yapf",
                "--in-place",
                "--style",
                "pyproject.toml",
                str(path),
            ],
            check=True,
        )
    print(f"Formatted {len(files)} Python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
