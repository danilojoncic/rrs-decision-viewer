from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.decision_repository import (
    PREFIXED_NON_RRS_RE,
    _extract_keyword_rrs_refs,
    _extract_prefixed_refs,
    _normalize_rule_prefix,
    _normalize_rules,
)


DEFAULT_DECISIONS_DIR = ROOT / "data" / "decisions"
TEXT_FIELDS = ("procedural_matters", "facts", "conclusions", "decision")
CONTEXTUAL_RRS_RE = re.compile(
    r"\b(?:as\s+per|in\s+accordance\s+with|according\s+to|pursuant\s+to)\s+"
    r"(?P<ref>[A-Z]\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)",
    re.IGNORECASE,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize decision rule fields and infer missing rules from explicit case text."
    )
    parser.add_argument("--decisions-dir", type=Path, default=DEFAULT_DECISIONS_DIR)
    parser.add_argument("--apply", action="store_true", help="Write changes to JSON files.")
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Also scan JSON files in hidden folders such as .drafts.",
    )
    parser.add_argument("--examples", type=int, default=20)
    args = parser.parse_args()

    updates: list[tuple[Path, list[str], list[str], str]] = []
    unresolved: list[Path] = []

    for path in _iter_json_files(args.decisions_dir, include_hidden=args.include_hidden):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        raw_rules = _as_list(data.get("rules"))
        normalized_rules = _normalize_rules(raw_rules)
        inferred_rules = _infer_rules(data)

        if normalized_rules:
            fixed_rules = normalized_rules
            reason = "normalized existing rules"
        elif inferred_rules:
            fixed_rules = inferred_rules
            reason = "inferred from case text"
        else:
            unresolved.append(path)
            continue

        if raw_rules == fixed_rules:
            continue

        updates.append((path, raw_rules, fixed_rules, reason))
        if args.apply:
            data["rules"] = fixed_rules
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    action = "Updated" if args.apply else "Would update"
    print(f"{action} {len(updates)} JSON files.")
    print(f"Unresolved missing-rule files: {len(unresolved)}")

    if updates:
        print()
        print("Examples:")
        for path, before, after, reason in updates[: args.examples]:
            print(f"- {path.relative_to(ROOT)} ({reason})")
            print(f"  before: {before}")
            print(f"  after:  {after}")

    if unresolved:
        print()
        print("Unresolved examples:")
        for path in unresolved[: args.examples]:
            print(f"- {path.relative_to(ROOT)}")


def _iter_json_files(root: Path, *, include_hidden: bool) -> list[Path]:
    paths = []
    for path in root.rglob("*.json"):
        if not include_hidden and any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        paths.append(path)
    return sorted(paths, key=lambda item: str(item).casefold())


def _infer_rules(data: dict[str, Any]) -> list[str]:
    inferred: list[str] = []
    for text in _as_list(data.get("rules")):
        inferred.extend(_normalize_rules([text]))

    for field in TEXT_FIELDS:
        for text in _as_list(data.get(field)):
            inferred.extend(_extract_explicit_rules_from_text(text))

    return _dedupe_rules(inferred)


def _extract_explicit_rules_from_text(text: str) -> list[str]:
    inferred: list[str] = []
    inferred.extend(_extract_keyword_rrs_refs(text))

    for match in PREFIXED_NON_RRS_RE.finditer(text):
        inferred.extend(
            _extract_prefixed_refs(
                text[match.end() :],
                _normalize_rule_prefix(match.group("prefix")),
            )
        )

    for match in CONTEXTUAL_RRS_RE.finditer(text):
        if not match.group("ref")[0].isalpha():
            continue
        inferred.extend(_normalize_rules([f"RRS {match.group('ref')}"]))

    return _dedupe_rules(inferred)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    text = _clean_text(value)
    return [text] if text else []


def _clean_text(value: Any) -> str:
    return " ".join(str(value).split())


def _dedupe_rules(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = re.sub(r"[^a-z0-9]+", "", value.casefold())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


if __name__ == "__main__":
    main()
