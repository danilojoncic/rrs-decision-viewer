"""Regression checks for data that must never enter a published build."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_cases import MAX_FILE_BYTES, validate_case  # noqa: E402


def expect_rejected(path: Path, message: str) -> None:
    try:
        validate_case(path)
    except ValueError:
        return
    raise AssertionError(message)


with tempfile.TemporaryDirectory() as temporary_directory:
    directory = Path(temporary_directory)
    case = directory / "case.json"
    case.write_text(json.dumps({"event": "Safe event", "facts": []}), encoding="utf-8")
    validate_case(case)

    case.write_text(
        json.dumps({"event": "Safe event", "jury": {"type": "Panel", "chair": "Name", "members": []}}),
        encoding="utf-8",
    )
    validate_case(case)

    case.write_text(json.dumps({"event": "Unsafe", "unexpected": "value"}), encoding="utf-8")
    expect_rejected(case, "an unexpected field was accepted")

    case.write_bytes(b" " * (MAX_FILE_BYTES + 1))
    expect_rejected(case, "an oversized file was accepted")

    target = directory / "target.json"
    target.write_text(json.dumps({"event": "Safe event"}), encoding="utf-8")
    link = directory / "link.json"
    link.symlink_to(target)
    expect_rejected(link, "a symbolic link was accepted")

print("Security validation checks passed.")
