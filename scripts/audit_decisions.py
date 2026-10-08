from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_decisions_dir, get_imports_dir
from app.services.decision_repository import DecisionRepository


NOISY_RULE_TERMS = ("case details", "case decision", "powered by", "as of", "page ")
NOISY_JUDGE_TERMS = ("signed", "date:", "time:", "____")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit the decision index after repository normalization."
    )
    parser.add_argument("--examples", type=int, default=8, help="Number of examples to show.")
    args = parser.parse_args()

    repository = DecisionRepository(get_decisions_dir(), get_imports_dir())
    records = repository.all()
    facets = repository.facets()

    print(f"records: {len(records)}")
    print(f"unique events: {len(facets['events'])}")
    print(f"unique request types: {len(facets['request_types'])}")
    print(f"unique rules: {len(facets['rules'])}")
    print(f"unique judges: {len(facets['judges'])}")
    print(f"records needing review: {repository.review_count()}")
    print()

    print_top("top rules", facets["rules"], args.examples)
    print_top("top judges", facets["judges"], args.examples)

    changed_rules = rule_cleanup_examples(records)
    changed_judges = judge_cleanup_examples(records)
    suspect_rules = suspect_rule_examples(records)
    suspect_judges = suspect_judge_examples(records)
    review_flags = Counter(flag for record in records for flag in record.review_flags)

    print(f"rule fields normalized: {len(changed_rules)}")
    print_examples(changed_rules, args.examples)
    print(f"judge fields normalized: {len(changed_judges)}")
    print_examples(changed_judges, args.examples)

    print(f"remaining suspect rule displays: {len(suspect_rules)}")
    print_examples(suspect_rules, args.examples)
    print(f"remaining suspect judge displays: {len(suspect_judges)}")
    print_examples(suspect_judges, args.examples)

    if review_flags:
        print()
        print("review flags:")
        for flag, count in review_flags.most_common(args.examples):
            print(f"  {count:>4}  {flag}")


def print_top(title: str, values: list[tuple[str, int]], limit: int) -> None:
    print(f"{title}:")
    for label, count in values[:limit]:
        print(f"  {count:>4}  {label}")
    print()


def print_examples(values: list[str], limit: int) -> None:
    if not values:
        print("  none")
        print()
        return

    for value in values[:limit]:
        print(f"  - {value}")
    if len(values) > limit:
        print(f"  ... {len(values) - limit} more")
    print()


def rule_cleanup_examples(records: Iterable[object]) -> list[str]:
    examples: list[str] = []
    for record in records:
        raw_rules = raw_list(record.raw.get("rules"))
        if raw_rules != record.rules:
            examples.append(
                f"{record.relative_path}: {truncate(raw_rules)} -> {truncate(record.rules)}"
            )
    return examples


def judge_cleanup_examples(records: Iterable[object]) -> list[str]:
    examples: list[str] = []
    for record in records:
        jury = record.raw.get("jury") if isinstance(record.raw.get("jury"), dict) else {}
        raw_judges = [*raw_list(jury.get("chair")), *raw_list(jury.get("members"))]
        if raw_judges != record.judges:
            examples.append(
                f"{record.relative_path}: {truncate(raw_judges)} -> {truncate(record.judges)}"
            )
    return examples


def suspect_rule_examples(records: Iterable[object]) -> list[str]:
    examples: list[str] = []
    for record in records:
        for rule in record.rules:
            folded = rule.casefold()
            if len(rule) > 80 or any(term in folded for term in NOISY_RULE_TERMS):
                examples.append(f"{record.relative_path}: {rule}")
    return examples


def suspect_judge_examples(records: Iterable[object]) -> list[str]:
    examples: list[str] = []
    for record in records:
        for judge in record.judges:
            folded = judge.casefold()
            if len(judge) > 60 or any(term in folded for term in NOISY_JUDGE_TERMS):
                examples.append(f"{record.relative_path}: {judge}")
    return examples


def raw_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


def clean_text(value: object) -> str:
    return " ".join(str(value).split())


def truncate(value: object, limit: int = 160) -> str:
    text = repr(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


if __name__ == "__main__":
    main()
