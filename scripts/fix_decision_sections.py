#!/usr/bin/env python3
"""Clean obvious extraction noise from conclusion and decision sections."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS_DIR = ROOT / "data" / "decisions"

DECISION_LABEL_RE = re.compile(
    r"\b(?P<label>"
    r"Decision from the original hearing|Decision original hearing|Original Decision|"
    r"Decision from the reopened hearing|Decision reopened hearing|"
    r"Decision of the reopened hearing|Reopening Decision"
    r")\s*:\s*",
    re.IGNORECASE,
)
CONCLUSION_LABEL_RE = re.compile(
    r"\b(?P<label>"
    r"Conclusions? from the reopened hearing(?:\s*:\s*Conclusion\s+\d+\s+is\s+replaced\s+by)?|"
    r"Conclusions? of the reopened hearing|Conclusion of the reopened hearing|"
    r"Conclusion reopened hearing|Conclusions? and Rules for the reopened hearing|"
    r"Conclusions? for the original hearing|Conclusions? for the reopening|"
    r"Original Conclusions|REOPENED HEARING(?!\s+conclusions?)|Reopened hearing(?!\s+conclusions?)"
    r")\s*:?",
    re.IGNORECASE,
)
CASE_DETAILS_RE = re.compile(
    r"\s*(?:[A-Z][A-Za-z0-9 ,.'’&/()\-]{0,90}\s+)?Case Details\s+As of\s+"
    r"\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+At\s+\d{1,2}:\d{2}",
    re.IGNORECASE,
)
ORIGINAL_DECISION_ANNOUNCED_RE = re.compile(
    r"\s*Original decision announced at \d{1,2}:\d{2} on \d{1,2}/\d{1,2}/\d{4}\s*",
    re.IGNORECASE,
)

JOINED_WORD_FIXES = (
    ("onstarboard", "on starboard"),
    ("tackcourse", "tack course"),
    ("shetried", "she tried"),
    ("luffed,but", "luffed, but"),
    ("sideabout", "side about"),
    ("capzised", "capsized"),
    ("hercrew", "her crew"),
    ("Crackof", "crack of"),
    ("itstank", "its tank"),
    ("onthe water", "on the water"),
    ("madesignificantly", "made significantly"),
    ("ofher", "of her"),
    ("ofthe", "of the"),
    ("appropriatepenalty", "appropriate penalty"),
    ("theright-of-way", "the right-of-way"),
    ("GER57398", "GER 57398"),
    ("GER57222", "GER 57222"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize obvious conclusion/decision extraction problems."
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
        notes = apply_manual_fixes(path.name, updated)
        for field in ("conclusions", "decision"):
            original = as_list(updated.get(field))
            cleaned = clean_section(field, original)
            if cleaned != original:
                updated[field] = cleaned
                notes.append(f"{field}: {len(original)} -> {len(cleaned)} items")

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
        note_text = "; ".join(notes) if notes else "section text normalized"
        print(f"- {path.relative_to(ROOT)}: {note_text}")
    remaining = len(changed) - args.examples
    if remaining > 0:
        print(f"... {remaining} more")
    return 0


def apply_manual_fixes(filename: str, data: dict[str, Any]) -> list[str]:
    if filename == "protest_13__150.json":
        data["facts"] = [
            "At race 4 of 420 yellow fleet, conditions on course Juliett were 15-17 knots of basic wind with gusts up to 20 knots and a choppy wave.",
            "25 seconds after the start, GER 57398 sailed on starboard tack.",
            "GER 57222 sailed on a converging port tack course, aiming at GER 57398’s port side on bow level.",
            "When GER 57222 became aware of GER 57398, she tried to bear away.",
            "When GER 57398 became aware of GER 57222, she luffed, but contact immediately occurred between the bow of GER 57222 and the port side of GER 57398 about 1 metre behind its bow.",
            "GER 57398 nearly capsized to windward, and her crew fell into the water.",
            "The damage at GER 57398’s starboard side was a crack of about 30 cm in the deck and about 20 cm in the hull, and the boat filled its tank with water.",
            "There was no damage to GER 57222’s bow.",
            "GER 57222 went to the race committee and informed them that they wanted to retire from race 4. She sailed and finished races 5 and 6.",
            "GER 57398 was not able to repair the damage on the water. She did not finish race 4, and she did not start races 5 and 6.",
        ]
        data["conclusions"] = [
            "GER 57222 on port tack failed to keep clear of GER 57398 on starboard tack, and broke RRS 10.",
            "GER 57222 did not avoid contact with GER 57398 even though it was reasonably possible, and broke RRS 14(a).",
            "It was not reasonably possible for GER 57398, the right-of-way boat, to avoid contact with GER 57222 when it became clear that GER 57222 was not keeping clear. GER 57398 did not break RRS 14(a).",
            "Since GER 57222 caused serious damage by her breach, her penalty was to retire as required by RRS 44.1(b).",
            "GER 57398’s score in races 4, 5, and 6 was made significantly worse through no fault of her own by physical damage because of the action of GER 57222, which was breaking RRS 10 and RRS 14 and took an appropriate penalty.",
        ]
        data["decision"] = [
            "Redress is given to GER 57398.",
            "GER 57398 is to be scored in races 4 and 5 points equal to the average, rounded upward to the nearest tenth of a point (0.05 to be rounded upward), of her points in all races in the series, except races 4, 5, and 6. No other boat’s score shall change.",
            "GER 57222 score is changed from DNS to RET.",
        ]
        return ["manual repair of duplicated decision section"]

    if filename == "protest_13__50.json":
        data["conclusions"] = [
            "Original hearing conclusions:",
            "When acquiring right of way through her own actions, GER 218418 failed to initially give GRE room to keep clear, and broke RRS 15.",
            "GER 218418 did not avoid contact with GRE even though it was reasonably possible, and broke RRS 14(a).",
            "It was not reasonably possible for GRE, the boat sailing within the room to which she was entitled, to avoid contact with GER 218418 when it became clear that GER 218418 was not giving room. GRE did not break RRS 14(a).",
            "GER 218418 to windward failed to keep clear of NOR 218401 to leeward, and broke RRS 11.",
            "GER 218418 did not avoid contact with NOR 218401 even though it was reasonably possible, and broke RRS 14(a).",
            "It was not reasonably possible for NOR 218401, the right-of-way boat, to avoid contact with GER 218418 when it became clear that GER 218418 was not keeping clear. NOR 218401 did not break RRS 14(a).",
            "Since NOR 218401 was compelled to break RRS 30.4 as a consequence of GER 218418 breaking RRS 11, she is exonerated under RRS 43.1(a) for this breach.",
            "Additional conclusions for the request for redress:",
            "There was neither an improper action nor improper omission of the race committee. Therefore, the requirements for redress in RRS 61.4(b)(1) are not met.",
            "NOR 218401’s score in race 2 was made significantly worse through no fault of her own by the action of GER 218418 breaking RRS 11 and RRS 14(a). However, there was no damage or injury. Therefore, the requirements for redress in RRS 61.4(b)(2) are not met.",
            "Additional conclusion on scoring:",
            "As NOR 218401 was exonerated under RRS 43.1(a) for breaking RRS 30.4, she shall not be scored BFD and the Race Committee shall not display her number in the abandoned race 2 under Notice 24.",
            "Reopened hearing conclusions:",
            "When acquiring right of way through her own actions, GER 218418 failed to initially give GRE room to keep clear, and broke RRS 15.",
            "GER 218418 did not avoid contact with GRE even though it was reasonably possible, and broke RRS 14(a).",
            "It was not reasonably possible for GRE, the boat sailing within the room to which she was entitled, to avoid contact with GER 218418 when it became clear that GER 218418 was not giving room. GRE did not break RRS 14(a).",
            "GER 218418 to windward failed to keep clear of NOR 218401 to leeward, and broke RRS 11.",
            "GER 218418 did not avoid contact with NOR 218401 even though it was reasonably possible, and broke RRS 14(a).",
            "It was not reasonably possible for NOR 218401, the right-of-way boat, to avoid contact with GER 218418 when it became clear that GER 218418 was not keeping clear. NOR 218401 did not break RRS 14(a).",
            "Since NOR 218401 was compelled to break RRS 30.4 as a consequence of GER 218418 breaking RRS 11, she is exonerated under RRS 43.1(a) for this breach.",
            "Since the race was abandoned and is expected to be resailed and GER 218418 had caused neither injury nor serious damage, she shall not be penalized under RRS 36(b).",
            "Additional conclusions for the request for redress:",
            "There was neither an improper action nor improper omission of the race committee. Therefore, the requirements for redress in RRS 61.4(b)(1) are not met.",
            "NOR 218401’s score in race 2 was made significantly worse through no fault of her own by the action of GER 218418 breaking RRS 11 and RRS 14(a). However, there was no damage or injury. Therefore, the requirements for redress in RRS 61.4(b)(2) are not met.",
            "Additional conclusion on scoring:",
            "As NOR 218401 was exonerated under RRS 43.1(a) for breaking RRS 30.4, she shall not be scored BFD and the Race Committee shall not display her number in the abandoned race 2 under Notice 24.",
        ]
        data["decision"] = [
            "Original hearing decision:",
            "GER 218418 is DSQ in race 2.",
            "Redress not given to NOR 218401.",
            "Because NOR 218401 was exonerated under RRS 43.1(a) for breaking RRS 30.4, NOR 218401 shall not be scored BFD and the Race Committee shall not display her sail number in the abandoned race 2.",
            "The Race Committee should republish Notice 24 without NOR 218401 included in it.",
            "Reopened hearing decision:",
            "The protest is upheld. Since RRS 36(b) applies, no penalty is imposed on GER 218418 under RRS 60.5(c)(3).",
            "Redress not given to NOR 218401.",
            "Because NOR 218401 was exonerated under RRS 43.1(a) for breaking RRS 30.4, NOR 218401 shall not be scored BFD and the Race Committee shall not display her sail number in the abandoned race 2.",
            "The Race Committee should republish Notice 24 without NOR 218401 included in it.",
        ]
        return ["manual repair of facts/conclusions copied into decision"]

    if filename == "warnemunde_woche_7__70.json":
        data["conclusions"] = [
            "GER 74, on port tack, did not keep clear of GER 923, on starboard tack, and broke RRS 10.",
            "GER 74 did not avoid contact when it was reasonably possible, and broke RRS 14.",
            "It was not reasonably possible for GER 923, the right-of-way boat, to avoid contact with GER 74 when it became clear that GER 74 was not keeping clear. GER 923 did not break RRS 14(a).",
            "The contact resulted in physical damage to GER 923, being localized above the waterline and not affecting the integrity of the hull or her ability to race. Therefore, RRS 44.1(b) did not apply.",
            "Since RRS 44.1(b) did not apply, GER 74 took an applicable One-Turn Penalty as required by SI 16.1(a).",
            "The loss of places by GER 923 resulted from her avoiding action and subsequent manoeuvre to disengage, not from the physical damage itself. A worsening of a boat's score caused by an avoiding manoeuvre is not, by itself, grounds for redress (World Sailing Case 110). The score of GER 923 was not made significantly worse by injury or physical damage, and the requirements of RRS 61.4(b)(2) are not met.",
        ]
        data["decision"] = [
            "GER 74 broke RRS 10 and RRS 14 and took an applicable penalty. No further penalty is applied. GER 74's score in race 2 stands.",
            "Redress is not given to GER 923.",
        ]
        return ["manual split of numbered conclusions and decision"]

    return []


def clean_section(field: str, items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        text = clean_text(item)
        text = tidy_joined_words(text)
        text = remove_boilerplate(text)
        parts = split_labels(field, text)
        cleaned.extend(part for part in parts if part)
    return dedupe(cleaned)


def split_labels(field: str, text: str) -> list[str]:
    label_re = DECISION_LABEL_RE if field == "decision" else CONCLUSION_LABEL_RE
    matches = list(label_re.finditer(text))
    if not matches:
        return [text] if text else []

    parts: list[str] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        parts.append(clean_text(preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = clean_text(text[match.end() : end])
        label = canonical_label(field, match.group("label"))
        if content:
            parts.append(f"{label} {content}")
        else:
            parts.append(label)
    return parts


def canonical_label(field: str, label: str) -> str:
    folded = clean_text(label).casefold()
    if field == "decision":
        if "original" in folded:
            return "Original hearing decision:"
        if "reopen" in folded:
            return "Reopened hearing decision:"
        return "Decision:"

    if "original" in folded:
        return "Original hearing conclusions:"
    if "conclusion" in folded and "replaced" in folded:
        number_match = re.search(r"conclusion\s+\d+", folded)
        number_text = number_match.group(0).title() if number_match else "Conclusion"
        return f"Reopened hearing conclusions: {number_text} is replaced by:"
    if "reopen" in folded:
        return "Reopened hearing conclusions:"
    return "Conclusions:"


def remove_boilerplate(text: str) -> str:
    text = CASE_DETAILS_RE.sub("", text)
    text = ORIGINAL_DECISION_ANNOUNCED_RE.sub(" ", text)
    text = re.sub(r"\bRule\(s\) applicable:\s*[^:]+(?=\s+Decision:)", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^(Reopened hearing conclusions:)\s+conclusions:\s*",
        r"\1 ",
        text,
        flags=re.IGNORECASE,
    )
    return clean_text(text)


def dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        normalized = clean_text(item).casefold()
        if not normalized:
            continue
        if result and clean_text(result[-1]).casefold() == normalized:
            continue
        result.append(item)
    return result


def is_heading(item: str) -> bool:
    text = clean_text(item)
    return text.endswith(":") and len(text) <= 90


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


def clean_text(value: object) -> str:
    return " ".join(str(value).split())


def tidy_joined_words(text: str) -> str:
    for source, replacement in JOINED_WORD_FIXES:
        text = text.replace(source, replacement)
    return clean_text(text)


if __name__ == "__main__":
    raise SystemExit(main())
