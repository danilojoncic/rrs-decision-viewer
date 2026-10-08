from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_casebook_data_path, get_casebook_pdf_path


CASE_START_PAGE = 76
CASE_END_PAGE = 327
CASE_HEADING_RE = re.compile(r"^CASE\s+(\d{1,3})$")
SECTION_RE = re.compile(
    r"^(Facts(?:\s+and\s+Protest\s+Committee\s+Decision"
    r"|\s+for\s+Questions?\s+[\d,\sand]+"
    r"|\s+for\s+Question\s+\d+)?"
    r"|Question\s*\d*|Answer\s*\d*|Decision|Example\s+\d+)$"
)
SOURCE_RE = re.compile(
    r"^(?:[A-Z]{2,4}\s*\d{4}/\d+|[A-Z]{2,4},\s*\d{4}/\d+"
    r"|[A-Z]{2,4}\s*\d{4};|World Sailing,?\s*\d{4}"
    r"|Revised by World Sailing\s*\d{4}|CAN\s*\d{4}"
    r"|USA,\s*\d{4}/\d+|GBR\s*\d{4}/\d+|RYA\s*\d{4}/\d+"
    r"|USSA\s*\d{4}/\d+)"
)
REFERENCE_START_RE = re.compile(
    r"^(?:Rule\s|Definitions?,|Part\s|Section\s|Appendix\s|Race Signals"
    r"|International Regulations|World Sailing Regulations?|Basic Principle"
    r"|Sportsmanship and the Rules|Introduction|Terminology)"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract World Sailing casebook cases from PDF.")
    parser.add_argument("--pdf", type=Path, default=get_casebook_pdf_path())
    parser.add_argument("--output", type=Path, default=get_casebook_data_path())
    parser.add_argument("--start-page", type=int, default=CASE_START_PAGE)
    parser.add_argument("--end-page", type=int, default=CASE_END_PAGE)
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include deleted and withdrawn case stubs in the output.",
    )
    args = parser.parse_args()

    cases = parse_pdf(args.pdf, args.start_page, args.end_page)
    if not args.include_inactive:
        cases = [case for case in cases if case["status"] == "Active"]

    payload = {
        "title": "The Case Book for 2025-2028",
        "source_pdf": str(args.pdf),
        "source_page_range": [args.start_page, args.end_page],
        "includes_inactive_cases": args.include_inactive,
        "case_count": len(cases),
        "cases": cases,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cases)} cases to {args.output}")


def parse_pdf(pdf_path: Path, start_page: int, end_page: int) -> list[dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise SystemExit(
            "pdfplumber is required. Install requirements or run with the bundled Codex Python."
        ) from exc

    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    with pdfplumber.open(pdf_path) as pdf:
        for page_number in range(start_page, end_page + 1):
            text = pdf.pages[page_number - 1].extract_text(layout=False) or ""
            for raw_line in text.splitlines():
                line = clean_line(raw_line)
                if not line:
                    continue

                case_match = CASE_HEADING_RE.match(line)
                if case_match:
                    if current is not None:
                        blocks.append(current)
                    current = {
                        "case_number": int(case_match.group(1)),
                        "start_page": page_number,
                        "end_page": page_number,
                        "lines": [line],
                    }
                    continue

                if current is not None:
                    current["lines"].append(line)
                    current["end_page"] = page_number

    if current is not None:
        blocks.append(current)

    return [parse_case_block(block) for block in blocks]


def parse_case_block(block: dict[str, Any]) -> dict[str, Any]:
    case_number = block["case_number"]
    lines = block["lines"][1:]
    source_pages = [block["start_page"], block["end_page"]]

    if lines and lines[0] in {"Deleted", "Withdrawn for Revision"}:
        return {
            "id": case_id(case_number),
            "case_number": case_number,
            "title": f"Case {case_number}",
            "status": lines[0],
            "rules": [],
            "summary": "",
            "sections": [],
            "source_note": "",
            "source_pages": source_pages,
        }

    first_section_index = next(
        (index for index, line in enumerate(lines) if SECTION_RE.match(line)),
        len(lines),
    )
    preamble = lines[:first_section_index]
    section_lines = lines[first_section_index:]
    rules, summary = split_preamble(preamble)
    sections, source_note = split_sections(section_lines)

    return {
        "id": case_id(case_number),
        "case_number": case_number,
        "title": f"Case {case_number}",
        "status": "Active",
        "rules": rules,
        "summary": " ".join(summary),
        "sections": sections,
        "source_note": source_note,
        "source_pages": source_pages,
    }


def split_preamble(lines: list[str]) -> tuple[list[str], list[str]]:
    rules: list[str] = []
    summary: list[str] = []
    current_reference = ""
    in_summary = False

    for line in lines:
        if not in_summary and REFERENCE_START_RE.match(line):
            if current_reference:
                rules.append(current_reference)
            current_reference = line
            continue

        if not in_summary and current_reference and is_reference_continuation(line):
            current_reference = f"{current_reference} {line}"
            continue

        if current_reference:
            rules.append(current_reference)
            current_reference = ""
        in_summary = True
        summary.append(line)

    if current_reference:
        rules.append(current_reference)

    return rules, summary


def split_sections(lines: list[str]) -> tuple[list[dict[str, Any]], str]:
    sections: list[dict[str, Any]] = []
    source_notes: list[str] = []
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        if SOURCE_RE.match(line):
            source_notes.append(line)
            continue

        if SECTION_RE.match(line):
            if current_title:
                sections.append(
                    {
                        "key": section_key(current_title),
                        "title": current_title,
                        "items": paragraphs(current_lines),
                    }
                )
            current_title = line
            current_lines = []
            continue

        current_lines.append(line)

    if current_title:
        sections.append(
            {
                "key": section_key(current_title),
                "title": current_title,
                "items": paragraphs(current_lines),
            }
        )
    elif current_lines:
        sections.append({"key": "text", "title": "Text", "items": paragraphs(current_lines)})

    return sections, "; ".join(source_notes)


def paragraphs(lines: list[str]) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for line in lines:
        if SOURCE_RE.match(line):
            if current:
                items.append(" ".join(current))
                current = []
            items.append(line)
            continue

        if current and re.match(r"^(?:\(\d+\)|[a-z]\))", line):
            items.append(" ".join(current))
            current = [line]
            continue

        current.append(line)

    if current:
        items.append(" ".join(current))
    return items


def is_reference_continuation(line: str) -> bool:
    return len(line.split()) <= 7 and not line.endswith(".") and not SECTION_RE.match(line)


def section_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return key or "section"


def case_id(case_number: int) -> str:
    return f"world-sailing-case-{case_number:03d}"


def clean_line(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


if __name__ == "__main__":
    main()
