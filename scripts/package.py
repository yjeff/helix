"""Build a clean Helix source archive.

Usage:
    python scripts/package.py [-o helix.zip]
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".venv", "venv", "build", "dist", "out",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_NAMES = {".git-token", ".gitee-token"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path,
                        default=ROOT.parent / "helix.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if path.name in EXCLUDE_NAMES:
                continue
            if path.suffix in EXCLUDE_SUFFIXES:
                continue
            if ".egg-info" in str(rel):
                continue
            archive.write(path, Path(ROOT.name) / rel)
            count += 1
    print(f"{output} ({count} files)")


if __name__ == "__main__":
    main()
