#!/usr/bin/env python3
"""Repair known judge-name aliases and split extraction errors."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS_DIR = ROOT / "data" / "decisions"

JUDGE_ALIASES = {
    "paulineden": "Pauline den Burger",
    "paulinedenburger": "Pauline den Burger",
    "paulinedenburgerwilmink": "Pauline den Burger",
    "vicky": "Wai Kai Chan Vicky",
    "vickychan": "Wai Kai Chan Vicky",
    "vickywaikeichan": "Wai Kai Chan Vicky",
    "vickywaikaichan": "Wai Kai Chan Vicky",
    "waikei": "Wai Kai Chan Vicky",
    "waikeichan": "Wai Kai Chan Vicky",
    "waikeichanvicky": "Wai Kai Chan Vicky",
    "waikai": "Wai Kai Chan Vicky",
    "waikaichan": "Wai Kai Chan Vicky",
    "waikaichanvicky": "Wai Kai Chan Vicky",
    "weelee": "Wee Lee Willy",
    "weeleewilly": "Wee Lee Willy",
    "willyweelee": "Wee Lee Willy",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize known judge aliases and split judge-name extraction errors."
    )
    parser.add_argument("--decisions-dir", type=Path, default=DEFAULT_DECISIONS_DIR)
    parser.add_argument("--apply", action="store_true", help="Write changes to JSON files")
    parser.add_argument("--examples", type=int, default=12, help="Number of examples to show")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed: list[tuple[Path, str]] = []
    for path in sorted(args.decisions_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            continue
        jury = data.get("jury")
        if not isinstance(jury, dict):
            continue

        repaired = repair_jury(jury)
        if repaired != jury:
            data["jury"] = repaired
            changed.append((path, describe_change(jury, repaired)))
            if args.apply:
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

    verb = "Updated" if args.apply else "Would update"
    print(f"{verb} {len(changed)} JSON files.")
    for path, note in changed[: args.examples]:
        print(f"- {path.relative_to(ROOT)}: {note}")
    remaining = len(changed) - args.examples
    if remaining > 0:
        print(f"... {remaining} more")
    return 0


def repair_jury(jury: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(jury)
    chair = clean_name(jury.get("chair"))
    members = [clean_name(member) for member in as_list(jury.get("members"))]
    members = [member for member in members if member]

    chair, members = repair_split_chair(chair, members)
    chair = canonical_judge_name(chair)
    members = repair_member_splits(members)
    members = [canonical_judge_name(member) for member in members]
    members = dedupe_people([member for member in members if member and person_key(member) != person_key(chair)])

    repaired["chair"] = chair
    repaired["members"] = members
    return repaired


def repair_split_chair(chair: str, members: list[str]) -> tuple[str, list[str]]:
    if not members:
        return chair, members

    first = members[0]
    first_key = person_key(first)
    if person_key(chair) in {"waikei", "waikai"} and first.casefold().startswith("chan "):
        return "Wai Kai Chan Vicky", [clean_name(first[5:]), *members[1:]]

    if person_key(chair) == "weelee" and first_key == "willymyrtoantonopoulou":
        return "Wee Lee Willy", ["Myrto Antonopoulou", *members[1:]]

    if person_key(chair) == "paulineden" and first_key == "burgerwilminkwaikeichan":
        return "Pauline den Burger", ["Wai Kai Chan Vicky", *members[1:]]

    return chair, members


def repair_member_splits(members: list[str]) -> list[str]:
    repaired: list[str] = []
    index = 0
    while index < len(members):
        current = members[index]
        next_member = members[index + 1] if index + 1 < len(members) else ""
        current_key = person_key(current)
        next_key = person_key(next_member)

        if current_key == "vicky" and next_key in {"waikeichan", "waikaichan"}:
            repaired.append("Wai Kai Chan Vicky")
            index += 2
            continue

        if current_key in {"waikeichan", "waikaichan"} and next_key == "vicky":
            repaired.append("Wai Kai Chan Vicky")
            index += 2
            continue

        repaired.append(current)
        index += 1
    return repaired


def canonical_judge_name(name: str) -> str:
    return JUDGE_ALIASES.get(person_key(name), name)


def describe_change(original: dict[str, Any], repaired: dict[str, Any]) -> str:
    before = [clean_name(original.get("chair")), *[clean_name(member) for member in as_list(original.get("members"))]]
    after = [clean_name(repaired.get("chair")), *[clean_name(member) for member in as_list(repaired.get("members"))]]
    return f"{before} -> {after}"


def dedupe_people(names: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = person_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return [value] if value else []


def clean_name(value: object) -> str:
    text = " ".join(str(value or "").split()).strip(" -.);")
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+-\s*", " - ", text)
    return text


def person_key(value: str) -> str:
    normalized = clean_name(value).replace("ß", "ss")
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", normalized.casefold())


if __name__ == "__main__":
    raise SystemExit(main())
