#!/usr/bin/env python3
"""Format bunched facts, conclusions, and decisions without rewriting substance."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS_DIR = ROOT / "data" / "decisions"
TEXT_FIELDS = ("facts", "conclusions", "decision")

NUMBERED_MARKER_RE = re.compile(r"(?:(?<=^)|(?<=\s))\??(?P<num>\d{1,2})(?:\)|\.-|-)\s+")
BULLET_MARKER_RE = re.compile(r"(?:(?<=^)|(?<=\s))-\s+(?=[A-Z0-9])")
SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?])\s+(?=(?:[A-Z][a-z]|[A-Z]{2,}\s+\d|[0-9]{1,2}\s+[A-Z]{3}))"
)
ADDITIONAL_BOUNDARY_RE = re.compile(
    r"(?<=\))\s+(?=(?:It was|It is|NOR|NoR|SI|By|Since|Therefore|However|The|Redress|Using)\b)"
)
FACT_CHANGE_RE = re.compile(r"\b(?=Fact\s+\d+\s+is\s+changed\s+to:)", re.IGNORECASE)

SECTION_LABEL_PATTERNS = (
    (re.compile(r"\bOriginal Facts Found\s*:?", re.IGNORECASE), "Original facts found:"),
    (re.compile(r"\bFacts Found of the reopened hearing\s*:?", re.IGNORECASE), "Facts found of the reopened hearing:"),
    (re.compile(r"\bFacts found in the reopened hearing\s*:?", re.IGNORECASE), "Facts found in the reopened hearing:"),
    (re.compile(r"\bFacts found for the reopend hearing\s*:?", re.IGNORECASE), "Facts found for the reopened hearing:"),
    (re.compile(r"\bFacts found for the reopened hearing\s*:?", re.IGNORECASE), "Facts found for the reopened hearing:"),
    (re.compile(r"\bNew facts for the reopening\s*:?", re.IGNORECASE), "New facts for the reopening:"),
    (re.compile(r"\bAdditional facts for the Request for Redress\s*:?", re.IGNORECASE), "Additional facts for the request for redress:"),
    (re.compile(r"\bConclusions? Original Hearing\s*:?", re.IGNORECASE), "Original hearing conclusions:"),
    (re.compile(r"\bOriginal Conclusions\s*:?", re.IGNORECASE), "Original hearing conclusions:"),
    (re.compile(r"\bConclusions? of the reopened hearing\s*:?", re.IGNORECASE), "Reopened hearing conclusions:"),
    (re.compile(r"\bConclusions? for the reopening\s*:?", re.IGNORECASE), "Reopened hearing conclusions:"),
    (re.compile(r"\bDecision reopened hearing\s*:?", re.IGNORECASE), "Reopened hearing decision:"),
    (re.compile(r"\bReopening Decision\s*:?", re.IGNORECASE), "Reopened hearing decision:"),
    (re.compile(r"\bOriginal Decision\s*:?", re.IGNORECASE), "Original hearing decision:"),
    (re.compile(r"\bREOPENED HEARING(?!\s+(?:conclusions?|decision|facts?))\s*:?", re.IGNORECASE), "Reopened hearing:"),
    (re.compile(r"\bReopened hearing(?!\s+(?:conclusions?|decision|facts?))\s*:?", re.IGNORECASE), "Reopened hearing:"),
    (re.compile(r"\bOriginal hearing(?!\s+(?:conclusions?|decision|facts?))\s*:?", re.IGNORECASE), "Original hearing:"),
)

BOILERPLATE_PATTERNS = (
    re.compile(
        r"\s*Case Details\s+As of\s+"
        r"\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+At\s+\d{1,2}:\d{2}",
        re.IGNORECASE,
    ),
    re.compile(r"\s*Case Details\s*$", re.IGNORECASE),
    re.compile(r"\s*Case Decision\s+As of\s+\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+at\s+\d{1,2}:\d{2}", re.IGNORECASE),
    re.compile(r"\s*Case Decision\s+As of\s+[A-Z]{3}\s+\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+at\s+\d{1,2}:\d{2}", re.IGNORECASE),
    re.compile(r"\s*As of\s+[A-Z]{3}\s+\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+at\s+\d{1,2}:\d{2}", re.IGNORECASE),
    re.compile(r"^\s*Case Decision\s+", re.IGNORECASE),
    re.compile(r"\s*Powered\s*by\.?\s*\S*\s*", re.IGNORECASE),
    re.compile(r"\s*Report Created\s+[A-Z]{3}\s+\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+\d{1,2}:\d{2}\s*", re.IGNORECASE),
    re.compile(r"\s*Page\s+\d+\s+of\s+\d+\s*", re.IGNORECASE),
)

SPACE_FIXES = (
    (re.compile(r"\b([A-Z]{2,3})(\d{2,6})\b"), r"\1 \2"),
    (re.compile(r"\bboat\s*(?:lenght|length|hlength)s\b", re.IGNORECASE), "boat lengths"),
    (re.compile(r"\bboat\s*(?:lenght|length|hlength)\b", re.IGNORECASE), "boat length"),
    (re.compile(r"\bclose\s*hauled\b", re.IGNORECASE), "close-hauled"),
    (re.compile(r"\bright\s*of\s*way\b", re.IGNORECASE), "right-of-way"),
    (re.compile(r"\bmark\s*room\b", re.IGNORECASE), "mark-room"),
    (re.compile(r"\bkeepclear\b", re.IGNORECASE), "keep clear"),
    (re.compile(r"\broomto\b", re.IGNORECASE), "room to"),
    (re.compile(r"\bcontactbetween\b", re.IGNORECASE), "contact between"),
    (re.compile(r"\boccurredbetween\b", re.IGNORECASE), "occurred between"),
    (re.compile(r"\bdistancebetween\b", re.IGNORECASE), "distance between"),
    (re.compile(r"\bstarboardtack\b", re.IGNORECASE), "starboard tack"),
    (re.compile(r"\bporttack\b", re.IGNORECASE), "port tack"),
    (re.compile(r"\bwindwardof\b", re.IGNORECASE), "windward of"),
    (re.compile(r"\bleewardof\b", re.IGNORECASE), "leeward of"),
    (re.compile(r"\bbowof\b", re.IGNORECASE), "bow of"),
    (re.compile(r"\bsideof\b", re.IGNORECASE), "side of"),
    (re.compile(r"\bscorein\b", re.IGNORECASE), "score in"),
    (re.compile(r"\bcouldpass\b", re.IGNORECASE), "could pass"),
    (re.compile(r"\baimingto\b", re.IGNORECASE), "aiming to"),
    (re.compile(r"\btherequirements\b", re.IGNORECASE), "the requirements"),
    (re.compile(r"\bwasnot\b", re.IGNORECASE), "was not"),
    (re.compile(r"\bbecameclear\b", re.IGNORECASE), "became clear"),
    (re.compile(r"\bWhena\s+cquiring\b", re.IGNORECASE), "When acquiring"),
    (re.compile(r"\bfailedto\b", re.IGNORECASE), "failed to"),
    (re.compile(r"\bunderRRS\b", re.IGNORECASE), "under RRS"),
    (re.compile(r"\bItwas\b", re.IGNORECASE), "It was"),
    (re.compile(r"\bandtherefore\b", re.IGNORECASE), "and therefore"),
    (re.compile(r"\brace(\d+)\b", re.IGNORECASE), r"race \1"),
    (re.compile(r"\bof(\d+)\b", re.IGNORECASE), r"of \1"),
    (re.compile(r"\b([A-Z]{2,3})(\d{2,6})(?=[a-z])"), r"\1 \2 "),
    (re.compile(r"(\d)(?=(?:room|while|was|is)\b)", re.IGNORECASE), r"\1 "),
    (re.compile(r"\b1([A-Z]{3}\s?\d)", re.IGNORECASE), r"\1"),
    (re.compile(r"(\d)(and)\b", re.IGNORECASE), r"\1 \2"),
    (re.compile(r"\s+([,.;:])"), r"\1"),
    (re.compile(r"([,.;:])(?=[A-Za-z])"), r"\1 "),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Improve paragraph spacing for facts, conclusions, and decisions."
    )
    parser.add_argument("--decisions-dir", type=Path, default=DEFAULT_DECISIONS_DIR)
    parser.add_argument("--apply", action="store_true", help="Write changes to JSON files")
    parser.add_argument("--examples", type=int, default=12, help="Number of examples to show")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed: list[tuple[Path, list[str]]] = []

    for path in sorted(args.decisions_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            continue

        updated = json.loads(json.dumps(data, ensure_ascii=False))
        notes: list[str] = []
        for field in TEXT_FIELDS:
            original = as_list(updated.get(field))
            formatted = format_items(original, event=clean_text(updated.get("event")))
            if formatted != original:
                updated[field] = formatted
                notes.append(f"{field}: {len(original)} -> {len(formatted)}")

        if updated != data:
            changed.append((path, notes))
            if args.apply:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

    verb = "Updated" if args.apply else "Would update"
    print(f"{verb} {len(changed)} JSON files.")
    for path, notes in changed[: args.examples]:
        print(f"- {path.relative_to(ROOT)}: {'; '.join(notes)}")
    remaining = len(changed) - args.examples
    if remaining > 0:
        print(f"... {remaining} more")
    return 0


def format_items(items: list[str], event: str = "") -> list[str]:
    formatted: list[str] = []
    for item in items:
        text = normalize_spacing(item)
        text = remove_boilerplate(text, event)
        for part in split_section_labels(text):
            for subpart in split_fact_changes(part):
                for numbered_part in split_numbered_or_bulleted(subpart):
                    formatted.extend(split_long_sentences(numbered_part))
    return dedupe_adjacent([item for item in formatted if item])


def split_section_labels(text: str) -> list[str]:
    parts = [text]
    for pattern, canonical_label in SECTION_LABEL_PATTERNS:
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(split_on_label(part, pattern, canonical_label))
        parts = next_parts
    return [normalize_spacing(part) for part in parts if normalize_spacing(part)]


def split_on_label(text: str, pattern: re.Pattern[str], canonical_label: str) -> list[str]:
    matches = list(pattern.finditer(text))
    if not matches:
        return [text]

    parts: list[str] = []
    previous_end = 0
    for index, match in enumerate(matches):
        if should_ignore_label_match(text, match):
            continue
        before = text[previous_end : match.start()].strip()
        if before:
            parts.append(before)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.end() : end].strip()
        parts.append(canonical_label)
        if content:
            parts.append(content)
        previous_end = end
    tail = text[previous_end:].strip()
    if tail:
        parts.append(tail)
    return parts


def should_ignore_label_match(text: str, match: re.Match[str]) -> bool:
    before = normalize_spacing(text[: match.start()]).casefold()
    if (
        before.endswith("of the")
        or before.endswith("of an")
        or before.endswith("of a")
        or before.endswith("at the")
        or before.endswith("to the")
        or before.endswith("the")
    ):
        return True
    if before.endswith("facts found in the") or before.endswith("facts found of the"):
        return True
    return False


def split_fact_changes(text: str) -> list[str]:
    pieces = [piece.strip() for piece in FACT_CHANGE_RE.split(text) if piece.strip()]
    return pieces if len(pieces) > 1 else [text]


def split_numbered_or_bulleted(text: str) -> list[str]:
    numbered_parts = split_by_marker(text, NUMBERED_MARKER_RE, allow_preamble=True)
    if len(numbered_parts) > 1:
        return numbered_parts

    bullet_parts = split_by_marker(text, BULLET_MARKER_RE, allow_preamble=False)
    return bullet_parts if len(bullet_parts) > 1 else [text]


def split_by_marker(text: str, marker_re: re.Pattern[str], *, allow_preamble: bool) -> list[str]:
    matches = list(marker_re.finditer(text))
    if len(matches) < 2:
        return [text]

    starts = [match.start() for match in matches]
    if starts[0] > 3 and not allow_preamble:
        return [text]

    parts: list[str] = []
    if starts[0] > 3:
        preamble = normalize_spacing(text[: starts[0]].strip(" -"))
        if preamble:
            parts.append(preamble)

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        part = marker_re.sub("", text[start:end], count=1).strip(" -")
        if part:
            parts.append(normalize_spacing(part))
    return parts if len(parts) > 1 else [text]


def split_long_sentences(text: str) -> list[str]:
    if len(text) <= 520 or is_heading(text):
        return [text]

    intermediate: list[str] = []
    for piece in SENTENCE_BOUNDARY_RE.split(text):
        intermediate.extend(ADDITIONAL_BOUNDARY_RE.split(piece))
    pieces = [piece.strip() for piece in intermediate if piece.strip()]
    if len(pieces) <= 1:
        return [text]
    return [normalize_spacing(piece) for piece in pieces]


def remove_boilerplate(text: str, event: str = "") -> str:
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub(" ", text)
    text = normalize_spacing(text)
    if event and text.casefold() in {
        f"{event.casefold()} facts",
        f"{event.casefold()} decision",
        f"{event.casefold()} conclusions",
    }:
        return ""
    if event and text.casefold().endswith(event.casefold()):
        text = text[: -len(event)].rstrip(" -")
    if event and text.casefold().startswith(f"{event.casefold()} "):
        remainder = text[len(event) :].strip(" -")
        if re.match(r"(?:[A-Z]{2,4}\b|\d|Leg\b|At\b|Both\b|No\b|There\b)", remainder):
            text = remainder
    return normalize_spacing(text)


def normalize_spacing(value: object) -> str:
    text = " ".join(str(value).split())
    for pattern, replacement in SPACE_FIXES:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def dedupe_adjacent(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if result and result[-1].casefold() == item.casefold():
            continue
        result.append(item)
    return result


def is_heading(text: str) -> bool:
    return text.endswith(":") and len(text) <= 90


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


if __name__ == "__main__":
    raise SystemExit(main())
