from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RULE_REF_RE = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"(?:"
    r"R?\d+(?:\.\d+)*[a-z](?:\d+)?"
    r"|[A-Z]\d+(?:\.\d+)*(?:\([a-z0-9]+\))*"
    r"|R?\d+(?:\.\d+)*(?:\([a-z0-9]+\))*"
    r")"
    r"(?![A-Za-z0-9.])",
    re.IGNORECASE,
)

COMPACT_RULE_REF_RE = re.compile(
    r"^(?:rules?|rrs)?\s*"
    r"(?P<ref>R?\d+(?:\.\d+)*[a-z](?:\d+)?|[A-Z]\d+(?:\.\d+)*|R?\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CasebookSection:
    key: str
    title: str
    items: list[str]


@dataclass(frozen=True)
class CasebookCase:
    id: str
    case_number: int
    title: str
    status: str
    rules: list[str]
    summary: str
    sections: list[CasebookSection]
    source_note: str
    source_pages: list[int]
    rule_keys: list[str]
    rule_key_set: frozenset[str]
    search_blob: str

    @property
    def is_active(self) -> bool:
        return self.status == "Active"

    @property
    def page_label(self) -> str:
        if not self.source_pages:
            return ""
        start_page = self.source_pages[0]
        end_page = self.source_pages[-1]
        if start_page == end_page:
            return f"PDF page {start_page}"
        return f"PDF pages {start_page}-{end_page}"

    @property
    def study_sections(self) -> list[CasebookSection]:
        sections: list[CasebookSection] = []
        if self.summary:
            sections.append(
                CasebookSection(key="summary", title="Case Summary", items=[self.summary])
            )
        if self.rules:
            sections.append(CasebookSection(key="rules", title="Rules", items=self.rules))
        sections.extend(self.sections)
        source_items = [item for item in [self.page_label, self.source_note] if item]
        if source_items:
            sections.append(
                CasebookSection(key="source", title="Source", items=source_items)
            )
        return sections


class CasebookRepository:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self._signature: tuple[int, int] | None = None
        self._title = "World Sailing Casebook"
        self._cases: list[CasebookCase] = []
        self._cases_by_id: dict[str, CasebookCase] = {}
        self._case_index_by_id: dict[str, int] = {}
        self._facets: dict[str, list[tuple[str, int]]] = {"statuses": [], "rules": []}
        self._rule_display_by_key: dict[str, str] = {}
        self._search_cache: dict[tuple[object, ...], list[CasebookCase]] = {}
        self._search_cache_limit = 128

    @property
    def title(self) -> str:
        self._refresh_if_changed()
        return self._title

    def all(self) -> list[CasebookCase]:
        self._refresh_if_changed()
        return self._cases

    def get(self, case_id: str) -> CasebookCase | None:
        self._refresh_if_changed()
        return self._cases_by_id.get(case_id)

    def search(
        self,
        *,
        q: str = "",
        status: str = "",
        rules: list[str] | None = None,
    ) -> list[CasebookCase]:
        self._refresh_if_changed()
        selected_rule_keys = _rule_filter_keys(rules or [])
        terms = [_search_key(term) for term in re.findall(r"\S+", q)]
        normalized_status = _clean_text(status)
        cache_key = (
            " ".join(terms),
            normalized_status,
            tuple(sorted(selected_rule_keys)),
        )
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        results: list[CasebookCase] = []
        for case in self._cases:
            if normalized_status and case.status != normalized_status:
                continue
            if selected_rule_keys and not selected_rule_keys.intersection(case.rule_key_set):
                continue
            if terms and not all(term in case.search_blob for term in terms):
                continue
            results.append(case)
        if len(self._search_cache) >= self._search_cache_limit:
            self._search_cache.pop(next(iter(self._search_cache)))
        self._search_cache[cache_key] = results
        return results

    def facets(self) -> dict[str, list[tuple[str, int]]]:
        self._refresh_if_changed()
        return self._facets

    def canonical_rule_filters(self, values: list[str]) -> set[str]:
        self._refresh_if_changed()
        selected: set[str] = set()
        for value in values:
            keys = _rule_keys(value)
            if keys:
                selected.update(self._rule_display_by_key.get(key, value) for key in keys)
        return selected

    def neighbors(self, case_id: str) -> tuple[CasebookCase | None, CasebookCase | None]:
        cases = self.all()
        index = self._case_index_by_id.get(case_id)
        if index is not None:
            previous_case = cases[index - 1] if index > 0 else None
            next_case = cases[index + 1] if index < len(cases) - 1 else None
            return previous_case, next_case
        return None, None

    def _refresh_if_changed(self) -> None:
        signature = self._current_signature()
        if signature == self._signature:
            return

        if not self.data_path.exists():
            self._title = "World Sailing Casebook"
            self._cases = []
            self._cases_by_id = {}
            self._case_index_by_id = {}
            self._facets = {"statuses": [], "rules": []}
            self._rule_display_by_key = {}
            self._search_cache.clear()
            self._signature = signature
            return

        payload = json.loads(self.data_path.read_text(encoding="utf-8"))
        self._title = _clean_text(payload.get("title")) or "World Sailing Casebook"
        cases = [
            case
            for case in (_load_case(item) for item in payload.get("cases", []))
            if case.is_active
        ]
        cases.sort(key=lambda case: case.case_number)
        self._cases = cases
        self._cases_by_id = {case.id: case for case in cases}
        self._case_index_by_id = {case.id: index for index, case in enumerate(cases)}
        self._rebuild_derived_indexes()
        self._search_cache.clear()
        self._signature = signature

    def _current_signature(self) -> tuple[int, int]:
        if not self.data_path.exists():
            return (0, 0)
        stat = self.data_path.stat()
        return (stat.st_size, stat.st_mtime_ns)

    def _rebuild_derived_indexes(self) -> None:
        cases = self._cases
        self._facets = {
            "statuses": _sorted_counter(case.status for case in cases if case.status),
            "rules": _sorted_counter_by_rule(rule for case in cases for rule in case.rules),
        }
        display_by_key: dict[str, str] = {}
        for rule, _count in self._facets["rules"]:
            for key in _rule_keys(rule):
                display_by_key.setdefault(key, rule)
        self._rule_display_by_key = display_by_key


def _load_case(data: dict[str, Any]) -> CasebookCase:
    rules = _as_list(data.get("rules"))
    sections = []
    for section in data.get("sections", []):
        if not isinstance(section, dict):
            continue
        title = _clean_text(section.get("title"))
        sections.append(
            CasebookSection(
                key=_section_key(title or _clean_text(section.get("key"))),
                title=title,
                items=_as_list(section.get("items")),
            )
        )
    fields_for_search = [
        _clean_text(data.get("title")),
        str(data.get("case_number", "")),
        _clean_text(data.get("status")),
        *rules,
        _clean_text(data.get("summary")),
        *[section.title for section in sections],
        *[item for section in sections for item in section.items],
        _clean_text(data.get("source_note")),
    ]
    rule_keys = sorted({key for rule in rules for key in _rule_keys(rule)})

    return CasebookCase(
        id=_clean_text(data.get("id")),
        case_number=int(data.get("case_number", 0)),
        title=_clean_text(data.get("title")),
        status=_clean_text(data.get("status")) or "Active",
        rules=rules,
        summary=_clean_text(data.get("summary")),
        sections=sections,
        source_note=_clean_text(data.get("source_note")),
        source_pages=[int(page) for page in data.get("source_pages", [])],
        rule_keys=rule_keys,
        rule_key_set=frozenset(rule_keys),
        search_blob=" ".join(_search_key(field) for field in fields_for_search),
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    text = _clean_text(value)
    return [text] if text else []


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _rule_keys(value: str) -> set[str]:
    text = _clean_text(value)
    compact_key = _compact_rule_ref_key(text)
    if compact_key:
        return {compact_key}

    keys = {_search_key(match.group(0)) for match in RULE_REF_RE.finditer(text)}
    if keys:
        return {key for key in keys if key}

    concept = re.sub(r"\b(?:and|the|rules?)\b", " ", text, flags=re.IGNORECASE)
    keys = {_search_key(concept)}
    return {key for key in keys if key}


def _compact_rule_ref_key(value: str) -> str:
    match = COMPACT_RULE_REF_RE.match(value.strip())
    if not match:
        return ""
    return _search_key(match.group("ref"))


def _section_key(title: str) -> str:
    normalized = _search_key(title)
    if normalized.startswith("facts"):
        return "facts"
    if normalized.startswith("question"):
        return "question"
    if normalized.startswith("answer"):
        return "answer"
    if normalized.startswith("decision"):
        return "decision"
    if normalized.startswith("example"):
        return "example"
    return normalized or "section"


def _rule_filter_keys(values: list[str]) -> set[str]:
    return {key for value in values for key in _rule_keys(value)}


def _search_key(value: Any) -> str:
    text = _clean_text(value).replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _sorted_counter(values: Any) -> list[tuple[str, int]]:
    counts = Counter(value for value in values if value)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))


def _sorted_counter_by_rule(values: Any) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    display_counts: dict[str, Counter[str]] = {}
    for value in values:
        keys = _rule_keys(value)
        display_key = sorted(keys)[0] if keys else _search_key(value)
        if not display_key:
            continue
        counts[display_key] += 1
        display_counts.setdefault(display_key, Counter())[value] += 1

    rows: list[tuple[str, int]] = []
    for key, count in counts.items():
        display = sorted(
            display_counts[key].items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )[0][0]
        rows.append((display, count))
    return sorted(rows, key=lambda item: (-item[1], item[0].casefold()))
