#!/usr/bin/env python3
"""Copy new decision JSON files into the Pages data folder and rebuild locally."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = ROOT / "data" / "decisions"
SAFE_FILENAME = re.compile(r"[^a-z0-9._-]+")


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts if part not in {path.anchor, ""})


def collect_json_files(sources: list[Path]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        source = source.expanduser()
        if not source.exists():
            raise FileNotFoundError(f"{source} does not exist")
        if source.is_file():
            if source.suffix.lower() == ".json" and not is_hidden(source):
                files.append(source)
            continue
        files.extend(
            path
            for path in sorted(source.rglob("*.json"))
            if path.is_file() and not is_hidden(path)
        )
    return sorted(dict.fromkeys(files))


def validate_json(path: Path) -> None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain one decision object")


def safe_filename(path: Path) -> str:
    stem = SAFE_FILENAME.sub("-", path.stem.lower()).strip("-._")
    return f"{stem or 'decision'}.json"


def available_path(target_dir: Path, filename: str) -> Path:
    candidate = target_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        candidate = target_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def rebuild_pages() -> None:
    commands = [
        [sys.executable, str(ROOT / "scripts" / "fix_judge_aliases.py"), "--apply"],
        [sys.executable, str(ROOT / "scripts" / "fix_missing_decision_rules.py"), "--apply"],
        [sys.executable, str(ROOT / "scripts" / "fix_decision_sections.py"), "--apply"],
        [sys.executable, str(ROOT / "scripts" / "format_decision_text.py"), "--apply"],
        [sys.executable, str(ROOT / "scripts" / "build_github_pages.py")],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import decision JSON files into data/decisions for GitHub Pages."
    )
    parser.add_argument("sources", nargs="+", type=Path, help="JSON files or folders to import")
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help="Destination folder, defaults to data/decisions",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Copy files only, without regenerating the local Pages data bundle",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = args.target_dir.expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    files = collect_json_files(args.sources)
    if not files:
        print("No visible JSON files found.")
        return 0

    copied: list[Path] = []
    for source in files:
        validate_json(source)
        destination = available_path(target_dir, safe_filename(source))
        shutil.copy2(source, destination)
        copied.append(destination)
        print(f"Imported {source} -> {display_path(destination)}")

    if not args.no_rebuild:
        rebuild_pages()

    print(f"Imported {len(copied)} decision JSON file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
