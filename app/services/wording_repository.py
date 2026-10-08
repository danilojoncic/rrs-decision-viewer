from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile


REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
RULE_RE = re.compile(r"(?<![A-Za-z0-9])(?:RRS\s*)?[A-Z]?\d+(?:\.\d+)*(?:\([a-z0-9]+\))*", re.I)


@dataclass(frozen=True)
class WordingEntry:
    id: str
    sheet: str
    label: str
    wording: str
    row_number: int
    kind: str
    placeholders: list[str]
    rules: list[str]
    search_blob: str

    @property
    def source_label(self) -> str:
        return f"{self.sheet}, row {self.row_number}"

    @property
    def label_or_kind(self) -> str:
        return self.label or self.kind


class WordingRepository:
    def __init__(self, workbook_path: Path) -> None:
        self.workbook_path = workbook_path
        self._signature: tuple[int, int] | None = None
        self._entries: list[WordingEntry] = []
        self._entries_by_id: dict[str, WordingEntry] = {}
        self._sheet_order: list[str] = []
        self._facets: dict[str, list[tuple[str, int]]] = {"sheets": [], "kinds": []}
        self._search_cache: dict[tuple[str, str, str], list[WordingEntry]] = {}
        self._search_cache_limit = 128

    def all(self) -> list[WordingEntry]:
        self._refresh_if_changed()
        return self._entries

    def get(self, entry_id: str) -> WordingEntry | None:
        self._refresh_if_changed()
        return self._entries_by_id.get(entry_id)

    def search(self, *, q: str = "", sheet: str = "", kind: str = "") -> list[WordingEntry]:
        self._refresh_if_changed()
        terms = [_search_key(term) for term in re.findall(r"\S+", q)]
        selected_sheet = _clean_text(sheet)
        selected_kind = _clean_text(kind)
        cache_key = (" ".join(terms), selected_sheet, selected_kind)
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        results: list[WordingEntry] = []
        for entry in self._entries:
            if selected_sheet and entry.sheet != selected_sheet:
                continue
            if selected_kind and entry.kind != selected_kind:
                continue
            if terms and not all(term in entry.search_blob for term in terms):
                continue
            results.append(entry)
        if len(self._search_cache) >= self._search_cache_limit:
            self._search_cache.pop(next(iter(self._search_cache)))
        self._search_cache[cache_key] = results
        return results

    def facets(self) -> dict[str, list[tuple[str, int]]]:
        self._refresh_if_changed()
        return self._facets

    def _refresh_if_changed(self) -> None:
        signature = self._current_signature()
        if signature == self._signature:
            return

        if not self.workbook_path.exists():
            self._entries = []
            self._entries_by_id = {}
            self._sheet_order = []
            self._facets = {"sheets": [], "kinds": []}
            self._search_cache.clear()
            self._signature = signature
            return

        sheets = _read_workbook_sheets(self.workbook_path)
        self._sheet_order = [sheet_name for sheet_name, _rows in sheets]
        entries: list[WordingEntry] = []
        for sheet_name, rows in sheets:
            entries.extend(_entries_from_sheet(sheet_name, rows))

        self._entries = entries
        self._entries_by_id = {entry.id: entry for entry in entries}
        self._facets = self._build_facets()
        self._search_cache.clear()
        self._signature = signature

    def _current_signature(self) -> tuple[int, int]:
        if not self.workbook_path.exists():
            return (0, 0)
        stat = self.workbook_path.stat()
        return (stat.st_size, stat.st_mtime_ns)

    def _build_facets(self) -> dict[str, list[tuple[str, int]]]:
        sheet_rank = {sheet: index for index, sheet in enumerate(self._sheet_order)}
        sheets = sorted(
            Counter(entry.sheet for entry in self._entries).items(),
            key=lambda item: (sheet_rank.get(item[0], 999), item[0].casefold()),
        )
        return {
            "sheets": sheets,
            "kinds": _sorted_counter(entry.kind for entry in self._entries),
        }


def _read_workbook_sheets(path: Path) -> list[tuple[str, list[tuple[int, dict[int, str]]]]]:
    with ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        rels = _read_workbook_relationships(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets: list[tuple[str, list[tuple[int, dict[int, str]]]]] = []
        for sheet in workbook.findall(f".//{SHEET_NS}sheet"):
            name = sheet.attrib.get("name", "Sheet")
            rel_id = sheet.attrib.get(f"{REL_NS}id")
            target = rels.get(rel_id or "")
            if not target:
                continue
            sheet_path = _sheet_target_path(target)
            rows = _read_sheet_rows(archive, sheet_path, shared_strings)
            sheets.append((name, rows))
        return sheets


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(f"{SHEET_NS}si"):
        values.append("".join(node.text or "" for node in item.iter() if node.tag == f"{SHEET_NS}t"))
    return values


def _read_workbook_relationships(archive: ZipFile) -> dict[str, str]:
    root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    return {
        rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
        for rel in root.findall(f"{PKG_REL_NS}Relationship")
    }


def _sheet_target_path(target: str) -> str:
    target = target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def _read_sheet_rows(
    archive: ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> list[tuple[int, dict[int, str]]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: list[tuple[int, dict[int, str]]] = []
    for row in root.findall(f".//{SHEET_NS}row"):
        row_number = int(row.attrib.get("r", len(rows) + 1))
        values: dict[int, str] = {}
        for cell in row.findall(f"{SHEET_NS}c"):
            reference = cell.attrib.get("r", "")
            column = _column_index(reference)
            value = _cell_value(cell, shared_strings)
            if value:
                values[column] = value
        if values:
            rows.append((row_number, values))
    return rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _clean_text("".join(node.text or "" for node in cell.iter() if node.tag == f"{SHEET_NS}t"))

    value_node = cell.find(f"{SHEET_NS}v")
    if value_node is None or value_node.text is None:
        return ""
    raw_value = value_node.text
    if cell_type == "s":
        try:
            return _clean_text(shared_strings[int(raw_value)])
        except (IndexError, ValueError):
            return ""
    return _clean_text(raw_value)


def _entries_from_sheet(
    sheet_name: str,
    rows: list[tuple[int, dict[int, str]]],
) -> list[WordingEntry]:
    entries: list[WordingEntry] = []
    current_label = ""
    for row_number, cells in rows:
        left = _clean_text(cells.get(1))
        wording = _clean_text("\n\n".join(value for column, value in sorted(cells.items()) if column > 1))

        if _is_header_row(left, wording):
            continue

        if left and not _looks_like_title(left):
            current_label = left

        if sheet_name == "Introduction" and left and not wording:
            wording = left
            left = "Introduction"
        elif not wording:
            continue

        label = left or current_label or sheet_name
        kind = _entry_kind(sheet_name, wording)
        placeholders = _unique(PLACEHOLDER_RE.findall(wording))
        rules = _rules_from_text(f"{label} {wording}")
        entry_id = f"{_slug(sheet_name)}-{row_number}"
        fields_for_search = [sheet_name, label, wording, kind, *placeholders, *rules]
        entries.append(
            WordingEntry(
                id=entry_id,
                sheet=sheet_name,
                label=label,
                wording=wording,
                row_number=row_number,
                kind=kind,
                placeholders=placeholders,
                rules=rules,
                search_blob=" ".join(_search_key(field) for field in fields_for_search),
            )
        )
    return entries


def _is_header_row(left: str, wording: str) -> bool:
    normalized_left = _search_key(left)
    normalized_wording = _search_key(wording)
    if not wording and _looks_like_title(left):
        return True
    return (
        normalized_left in {"matter", "rrs", "short"}
        and normalized_wording in {"wording", "decision"}
    )


def _looks_like_title(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    return bool(letters) and value.upper() == value and len(value) > 12


def _entry_kind(sheet_name: str, wording: str) -> str:
    lowered = wording.casefold()
    if sheet_name == "Introduction":
        return "Introduction"
    if lowered.startswith("note:"):
        return "Note"
    if "Decision:" in wording or sheet_name.endswith("Decisions"):
        return "Decision"
    if "Conclusion:" in wording or "Conclusions" in sheet_name or sheet_name in {"Validity", "Reopenings"}:
        return "Conclusion"
    if "Suggested Fact:" in wording:
        return "Fact"
    if "Procedural" in sheet_name:
        return "Procedural"
    return "Wording"


def _rules_from_text(value: str) -> list[str]:
    rules: list[str] = []
    for match in RULE_RE.finditer(value):
        text = match.group(0).strip()
        if not any(char.isdigit() for char in text):
            continue
        rules.append(re.sub(r"^RRS\s*", "", text, flags=re.I))
    return _unique(rules)


def _column_index(reference: str) -> int:
    letters = "".join(char for char in reference if char.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + ord(char.upper()) - ord("A") + 1
    return index


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _search_key(value: Any) -> str:
    text = _clean_text(value).replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "entry"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        key = _search_key(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _sorted_counter(values: Any) -> list[tuple[str, int]]:
    counts = Counter(value for value in values if value)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
