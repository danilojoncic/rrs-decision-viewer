from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SECTION_KEYS = ("procedural_matters", "facts", "rules", "conclusions", "decision")
CANONICAL_REQUEST_TYPES = {
    "Decision",
    "Formal Communication",
    "Protest",
    "Protest and Request for Redress",
    "Protest by PC",
    "Protest by RC",
    "Protest by TC",
    "Request for Redress",
    "Request for Redress by PC",
    "Request to Reopen",
    "Request to Reopen by PC",
    "Support Person",
}
REQUEST_TYPE_ALIASES = {
    "decision": "Decision",
    "formal communication": "Formal Communication",
    "formal comunication": "Formal Communication",
    "protest": "Protest",
    "protest upheld": "Protest",
    "protest by pc": "Protest by PC",
    "protest by rc": "Protest by RC",
    "protest by tc": "Protest by TC",
    "protest and redress": "Protest and Request for Redress",
    "protest and request for redress": "Protest and Request for Redress",
    "protest request for redress": "Protest and Request for Redress",
    "protest and risarcimento di danno": "Protest and Request for Redress",
    "request for redress": "Request for Redress",
    "request for redress by pc": "Request for Redress by PC",
    "request to reopen": "Request to Reopen",
    "reopening": "Request to Reopen",
    "reopening by pc": "Request to Reopen by PC",
    "support person": "Support Person",
    "video prova o registrazione della prova numero 2 ilca4": "Decision",
}
NOISY_RULE_PATTERNS = ("event:", "race number:", "case details", "powered by", "page ")
JUDGE_SUFFIX_TERMS = {
    "ARG",
    "AUT",
    "BRA",
    "CRO",
    "ESP",
    "FIN",
    "FRA",
    "GBR",
    "GER",
    "IND",
    "IRL",
    "ISR",
    "ITA",
    "JPN",
    "MNE",
    "NJ",
    "POR",
    "RSA",
    "SLO",
    "TUR",
    "USA",
    "IJ",
}
JUDGE_NAME_ALIASES = {
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
RULE_REF_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z]\d+(?:\.\d+)*(?:\([a-z0-9]+\))*|N\d+(?:\.\d+)*(?:\([a-z0-9]+\))*|\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
RULE_CONNECTOR_RE = re.compile(
    r"^(?=.*(?:\band\b|\bor\b|[,/&+\-()]))\s*(?:and|or|,|/|&|-|\+|\(|\))*\s*$",
    re.IGNORECASE,
)
SAILING_CASE_RE = re.compile(
    r"\b(?:(?:World Sailing|WS|Casebook)\s+)?Case\s+\d+\b", re.IGNORECASE
)
PREFIXED_NON_RRS_RE = re.compile(
    r"\b(?P<prefix>Star\s+Class\s+Rules?|Class\s+Rules?|SIs?|NoR|NOR|ORC|ESTR)\s+",
    re.IGNORECASE,
)
JUDGE_SPLIT_RE = re.compile(r"\s*(?:;|\n|\r)\s*")


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    filename: str
    source_label: str
    relative_path: str
    source_path: str
    origin_system: str
    request_type: str
    event: str
    race_number: str
    hearing_datetime: str
    parties: list[str]
    procedural_matters: list[str]
    facts: list[str]
    rules: list[str]
    conclusions: list[str]
    decision: list[str]
    jury_type: str
    jury_chair: str
    jury_members: list[str]
    judges: list[str]
    rule_keys: list[str]
    rule_key_set: frozenset[str]
    judge_keys: list[str]
    judge_key_set: frozenset[str]
    review_flags: list[str]
    needs_review: bool
    raw: dict[str, Any]
    search_blob: str


class DecisionRepository:
    def __init__(self, data_dir: Path, imports_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self.imports_dir = imports_dir
        self._records: list[DecisionRecord] = []
        self._records_by_id: dict[str, DecisionRecord] = {}
        self._record_index_by_id: dict[str, int] = {}
        self._signature: tuple[int, int, int] | None = None
        self._facets: dict[str, list[tuple[str, int]]] = {
            "events": [],
            "request_types": [],
            "origin_systems": [],
            "rules": [],
            "judges": [],
        }
        self._review_count = 0
        self._rule_display_by_key: dict[str, str] = {}
        self._judge_display_by_key: dict[str, str] = {}
        self._search_cache: dict[tuple[object, ...], list[DecisionRecord]] = {}
        self._search_cache_limit = 128
        self._state_cache: tuple[tuple[int, int, int], list[tuple[str, Path, Path]]] | None = None
        self._last_state_check_ns = 0
        self._state_check_interval_ns = 500_000_000

    def all(self) -> list[DecisionRecord]:
        self._refresh_if_changed()
        return self._records

    def get(self, decision_id: str) -> DecisionRecord | None:
        self._refresh_if_changed()
        return self._records_by_id.get(decision_id)

    def search(
        self,
        *,
        q: str = "",
        event: str = "",
        request_type: str = "",
        origin_system: str = "",
        rules: list[str] | None = None,
        judges: list[str] | None = None,
        needs_review: bool = False,
    ) -> list[DecisionRecord]:
        self._refresh_if_changed()
        selected_request_type = _normalize_request_type(request_type)
        selected_rule_keys = _rule_filter_keys(rules or [])
        selected_judge_keys = _judge_filter_keys(judges or [])
        terms = [term.casefold() for term in re.findall(r"\S+", q)]
        cache_key = (
            " ".join(terms),
            event,
            selected_request_type,
            origin_system,
            tuple(sorted(selected_rule_keys)),
            tuple(sorted(selected_judge_keys)),
            needs_review,
        )
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        results: list[DecisionRecord] = []
        for record in self._records:
            if event and record.event != event:
                continue
            if selected_request_type and record.request_type != selected_request_type:
                continue
            if origin_system and record.origin_system != origin_system:
                continue
            if needs_review and not record.needs_review:
                continue
            if selected_rule_keys and not selected_rule_keys.intersection(record.rule_key_set):
                continue
            if selected_judge_keys and not selected_judge_keys.issubset(record.judge_key_set):
                continue
            if terms and not all(term in record.search_blob for term in terms):
                continue
            results.append(record)
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
        for key in _rule_filter_keys(values):
            selected.add(self._rule_display_by_key.get(key, key))
        return selected

    def canonical_judge_filters(self, values: list[str]) -> set[str]:
        self._refresh_if_changed()
        selected: set[str] = set()
        for key in _judge_filter_keys(values):
            selected.add(self._judge_display_by_key.get(key, key))
        return selected

    def canonical_request_type_filter(self, value: str) -> str:
        return _normalize_request_type(value)

    def review_count(self) -> int:
        self._refresh_if_changed()
        return self._review_count

    def invalidate(self) -> None:
        self._signature = None
        self._state_cache = None
        self._search_cache.clear()
        self._last_state_check_ns = 0

    def neighbors(self, decision_id: str) -> tuple[DecisionRecord | None, DecisionRecord | None]:
        records = self.all()
        index = self._record_index_by_id.get(decision_id)
        if index is not None:
            previous_record = records[index - 1] if index > 0 else None
            next_record = records[index + 1] if index < len(records) - 1 else None
            return previous_record, next_record
        return None, None

    def raw_json(self, record: DecisionRecord) -> str:
        return json.dumps(record.raw, ensure_ascii=False, indent=2)

    def _refresh_if_changed(self) -> None:
        signature, files = self._current_state()
        if signature == self._signature:
            return

        records = [
            _load_record(root, path, source_label)
            for source_label, root, path in files
        ]
        records.sort(key=lambda record: (_natural_key(record.event), _natural_key(record.race_number), record.filename.casefold()))
        self._records = records
        self._records_by_id = {record.id: record for record in records}
        self._record_index_by_id = {record.id: index for index, record in enumerate(records)}
        self._rebuild_derived_indexes()
        self._signature = signature

    def _iter_json_files(self) -> list[tuple[str, Path, Path]]:
        files: list[tuple[str, Path, Path]] = []
        for source_label, root in self._source_roots():
            if not root.exists():
                continue
            for path in root.rglob("*.json"):
                relative_parts = path.relative_to(root).parts
                if any(part.startswith(".") for part in relative_parts):
                    continue
                files.append((source_label, root, path))
        return files

    def _current_state(self) -> tuple[tuple[int, int, int], list[tuple[str, Path, Path]]]:
        now_ns = time.monotonic_ns()
        if (
            self._state_cache is not None
            and now_ns - self._last_state_check_ns < self._state_check_interval_ns
        ):
            return self._state_cache

        files = self._iter_json_files()
        latest_mtime = 0
        total_size = 0
        for _source_label, _root, path in files:
            stat = path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime_ns)
            total_size += stat.st_size
        state = ((len(files), latest_mtime, total_size), files)
        self._state_cache = state
        self._last_state_check_ns = now_ns
        return state

    def _source_roots(self) -> list[tuple[str, Path]]:
        roots = [("base", self.data_dir)]
        if self.imports_dir is not None:
            roots.append(("imports", self.imports_dir))
        return roots

    def _rebuild_derived_indexes(self) -> None:
        records = self._records
        self._facets = {
            "events": _sorted_counter(record.event for record in records if record.event),
            "request_types": _sorted_counter(
                record.request_type for record in records if record.request_type
            ),
            "origin_systems": _sorted_counter(
                record.origin_system for record in records if record.origin_system
            ),
            "rules": _sorted_counter(rule for record in records for rule in record.rules),
            "judges": _sorted_counter_by_key(
                judge for record in records for judge in record.judges
            ),
        }
        self._review_count = sum(1 for record in records if record.needs_review)
        self._rule_display_by_key = {
            _rule_key(rule): rule for rule, _count in self._facets["rules"]
        }
        self._judge_display_by_key = {
            _person_key(judge): judge for judge, _count in self._facets["judges"]
        }
        self._search_cache.clear()


def _load_record(source_root: Path, path: Path, source_label: str) -> DecisionRecord:
    raw = json.loads(path.read_text(encoding="utf-8"))
    relative_path = f"{source_label}/{path.relative_to(source_root)}"
    jury = raw.get("jury") if isinstance(raw.get("jury"), dict) else {}

    raw_jury_chair = _as_text(jury.get("chair"))
    raw_jury_members = _as_list(jury.get("members"))
    jury_chair, jury_members = _normalize_jury(raw_jury_chair, raw_jury_members)
    judges = _dedupe_by_key([jury_chair, *jury_members], _person_key)
    raw_request_type = _as_text(raw.get("request_type"))
    request_type = _normalize_request_type(raw_request_type)
    raw_rules = _as_list(raw.get("rules"))
    rules = _normalize_rules(raw_rules)
    review_flags = _review_flags(
        raw_request_type=raw_request_type,
        request_type=request_type,
        raw_rules=raw_rules,
        normalized_rules=rules,
        raw_judges=[raw_jury_chair, *raw_jury_members],
        normalized_judges=judges,
    )

    fields_for_search = [
        relative_path,
        _as_text(raw.get("origin_system")),
        _as_text(raw.get("request_type")),
        _as_text(raw.get("event")),
        _as_text(raw.get("race_number")),
        _as_text(raw.get("hearing_datetime")),
        *_as_list(raw.get("parties")),
        *_as_list(raw.get("procedural_matters")),
        *_as_list(raw.get("facts")),
        *raw_rules,
        *rules,
        *_as_list(raw.get("conclusions")),
        *_as_list(raw.get("decision")),
    ]

    rule_keys = [_rule_key(rule) for rule in rules]
    judge_keys = [_person_key(judge) for judge in judges]

    return DecisionRecord(
        id=_make_id(relative_path),
        filename=path.name,
        source_label=source_label,
        relative_path=relative_path,
        source_path=str(path),
        origin_system=_as_text(raw.get("origin_system")),
        request_type=request_type,
        event=_as_text(raw.get("event")),
        race_number=_as_text(raw.get("race_number")),
        hearing_datetime=_as_text(raw.get("hearing_datetime")),
        parties=_as_list(raw.get("parties")),
        procedural_matters=_as_list(raw.get("procedural_matters")),
        facts=_as_list(raw.get("facts")),
        rules=rules,
        conclusions=_as_list(raw.get("conclusions")),
        decision=_as_list(raw.get("decision")),
        jury_type=_as_text(jury.get("type")),
        jury_chair=jury_chair,
        jury_members=jury_members,
        judges=judges,
        rule_keys=rule_keys,
        rule_key_set=frozenset(rule_keys),
        judge_keys=judge_keys,
        judge_key_set=frozenset(judge_keys),
        review_flags=review_flags,
        needs_review=bool(review_flags),
        raw=raw,
        search_blob=" ".join(fields_for_search).casefold(),
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return " ".join(str(value).split())


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    text = _as_text(value)
    return [text] if text else []


def _normalize_request_type(value: str) -> str:
    text = _as_text(value)
    if not text:
        return ""
    if "event:" in text.casefold() and "race number:" in text.casefold():
        return "Decision"

    key = _request_type_key(text)
    if key in REQUEST_TYPE_ALIASES:
        return REQUEST_TYPE_ALIASES[key]
    return _title_case_words(text)


def _request_type_key(value: str) -> str:
    text = _as_text(value).casefold()
    text = text.replace("&", " and ").replace("/", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_case_words(value: str) -> str:
    uppercase_words = {"PC", "RC", "TC"}
    words = []
    for word in _as_text(value).split():
        stripped = re.sub(r"[^A-Za-z]", "", word).upper()
        words.append(stripped if stripped in uppercase_words else word.capitalize())
    return " ".join(words)


def _normalize_rules(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        normalized.extend(_extract_rule_labels(value))
    return _dedupe(normalized)


def _extract_rule_labels(value: str) -> list[str]:
    text = _strip_rule_noise(value)
    if not text:
        return []

    labels: list[str] = []
    for case_match in SAILING_CASE_RE.finditer(text):
        labels.append(_title_case_label(case_match.group(0)))

    non_rrs_matches = list(PREFIXED_NON_RRS_RE.finditer(text))
    for non_rrs_match in non_rrs_matches:
        labels.extend(
            _extract_prefixed_refs(
                text[non_rrs_match.end() :],
                _normalize_rule_prefix(non_rrs_match.group("prefix")),
            )
        )

    keyword_labels = _extract_keyword_rrs_refs(text)
    if keyword_labels:
        labels.extend(keyword_labels)
    elif non_rrs_matches:
        return _dedupe(labels)
    elif _contains_only_rule_refs(text):
        labels.extend(f"RRS {_normalize_rule_ref(match.group(0))}" for match in RULE_REF_RE.finditer(text))
    else:
        labels.extend(_extract_leading_rrs_refs(text))

    return _dedupe(labels)


def _extract_keyword_rrs_refs(text: str) -> list[str]:
    labels: list[str] = []
    for match in re.finditer(r"\b(?:RRS|RSS|rules?|rule\(s\))\s*", text, re.IGNORECASE):
        prefix_context = text[max(0, match.start() - 18) : match.start()].casefold()
        if "rule" in match.group(0).casefold() and re.search(r"(?:star\s+)?class\s+$", prefix_context):
            continue
        labels.extend(_extract_rrs_refs(text[match.end() :]))
    return _dedupe(labels)


def _extract_prefixed_refs(text: str, prefix: str) -> list[str]:
    if prefix == "SI":
        annex_match = re.match(r"\s*Annex\s+(?P<annex>\d+)\s*(?::|\.|-)?\s*", text, re.IGNORECASE)
        if annex_match:
            annex_prefix = f"SI Annex {annex_match.group('annex')}"
            return _extract_prefixed_refs(text[annex_match.end() :], annex_prefix)

    refs: list[str] = []
    previous_end = 0
    for index, match in enumerate(RULE_REF_RE.finditer(text)):
        ref = _normalize_rule_ref(match.group(0))
        if _is_probable_year_or_page(ref) or _is_probable_non_rule_ref(prefix, ref):
            continue

        between = text[previous_end : match.start()]
        if (index == 0 and _is_valid_first_rule_gap(between)) or RULE_CONNECTOR_RE.match(between):
            refs.append(f"{prefix} {ref}")
            previous_end = match.end()
            continue

        break
    return refs


def _is_probable_non_rule_ref(prefix: str, ref: str) -> bool:
    return prefix == "ORC" and ref.isdigit() and int(ref) < 100


def _normalize_rule_prefix(prefix: str) -> str:
    key = re.sub(r"\s+", " ", prefix.casefold()).strip()
    if key in {"si", "sis"}:
        return "SI"
    if key == "nor":
        return "NoR"
    if key in {"class rule", "class rules"}:
        return "Class Rule"
    if key in {"star class rule", "star class rules"}:
        return "Star Class Rule"
    return prefix.upper()


def _extract_rrs_refs(text: str) -> list[str]:
    matches = list(RULE_REF_RE.finditer(text))
    if not matches:
        return []

    refs: list[str] = []
    previous_end = 0
    for index, match in enumerate(matches):
        ref = _normalize_rule_ref(match.group(0))
        if _is_probable_year_or_page(ref):
            continue

        between = text[previous_end : match.start()]
        if (index == 0 and _is_valid_first_rule_gap(between)) or RULE_CONNECTOR_RE.match(between):
            refs.append(f"RRS {ref}")
            previous_end = match.end()
            continue

        break
    return refs


def _is_valid_first_rule_gap(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"\s*(?:rules?|rule\(s\)|applicable|applies|:|,|;|/|&|-|\+|\(|\))*\s*",
            text,
            re.IGNORECASE,
        )
    )


def _strip_rule_noise(value: str) -> str:
    text = _as_text(value)
    text = re.split(
        r"\b(?:Case Details|Case Decision|As of|Powered by|Report Created|Page\s+\d+)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = _repair_rule_ref_text(text)
    return text.strip(" .;-:")


def _repair_rule_ref_text(text: str) -> str:
    text = re.sub(r"(\d(?:\.\d+)*)\s+\(([a-z0-9]+)\)", r"\1(\2)", text, flags=re.IGNORECASE)
    text = re.sub(r"(\([a-z0-9]+\))\s+\(([a-z0-9]+)\)", r"\1(\2)", text, flags=re.IGNORECASE)
    return re.sub(
        r"\b([A-Z]?\d+(?:\.\d+)*(?:\([a-z0-9]+\))+)(\d+)\b",
        lambda match: f"{match.group(1)}({match.group(2)})",
        text,
        flags=re.IGNORECASE,
    )


def _contains_only_rule_refs(text: str) -> bool:
    if len(text) > 80:
        return False
    without_refs = RULE_REF_RE.sub("", text)
    without_cases = SAILING_CASE_RE.sub("", without_refs)
    without_connectors = re.sub(r"\b(?:RRS|rule|rules|and|or)\b", "", without_cases, flags=re.IGNORECASE)
    return not re.search(r"[A-Za-z]{3,}", without_connectors)


def _normalize_rule_ref(ref: str) -> str:
    ref = ref.strip().upper()
    ref = re.sub(r"\(([A-Z0-9]+)\)", lambda match: f"({match.group(1).lower()})", ref)
    return ref


def _rule_key(rule: str) -> str:
    labels = _normalize_rules([rule])
    label = labels[0] if labels else _as_text(rule)
    folded = label.casefold()
    folded = re.sub(r"^rrs\s*", "", folded)
    return re.sub(r"[^a-z0-9]+", "", folded)


def _rule_filter_keys(values: list[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        labels = _normalize_rules([value])
        if labels:
            keys.update(_rule_key(label) for label in labels)
            continue

        key = _rule_key(value)
        if key:
            keys.add(key)
    return keys


def _judge_filter_keys(values: list[str]) -> set[str]:
    return {_person_key(judge) for judge in _normalize_judge_list(values) if _person_key(judge)}


def _is_probable_year_or_page(ref: str) -> bool:
    return ref.isdigit() and int(ref) > 200


def _title_case_label(label: str) -> str:
    if re.search(r"\bcase\b", label, re.IGNORECASE):
        case_number = re.search(r"\d+", label)
        return f"World Sailing Case {case_number.group(0)}" if case_number else label
    return label


def _extract_leading_rrs_refs(text: str) -> list[str]:
    first_match = RULE_REF_RE.search(text)
    if first_match is None:
        return []

    prefix = text[: first_match.start()]
    if not re.fullmatch(r"\s*(?:rules?|rule\(s\)|and|or|applicable:|rules applicable:)?\s*", prefix, re.IGNORECASE):
        return []

    return _extract_rrs_refs(text[first_match.start() :])


def _normalize_judge_list(values: list[str]) -> list[str]:
    names: list[str] = []
    for value in values:
        for part in _split_judge_value(value):
            normalized_name = _normalize_judge_name(part)
            if normalized_name:
                names.append(normalized_name)
    return _dedupe_by_key(names, _person_key)


def _normalize_jury(chair: str, members: list[str]) -> tuple[str, list[str]]:
    chair_names = _normalize_judge_list([chair])
    jury_chair = chair_names[0] if chair_names else ""
    jury_members = _normalize_judge_list([*chair_names[1:], *members])
    return jury_chair, jury_members


def _split_judge_value(value: str) -> list[str]:
    text = _as_text(value)
    text = re.sub(r"\)\s+(?=[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'.-]+\s)", ");", text)
    return [part for part in JUDGE_SPLIT_RE.split(text) if part]


def _normalize_judge_name(value: str) -> str:
    name = _as_text(value).strip(" -.);")
    if not name:
        return ""
    folded_name = name.casefold()
    if (
        ("signed" in folded_name and ("date" in folded_name or "_" in name))
        or "published:" in folded_name
        or "date:" in folded_name
        or "time:" in folded_name
    ):
        return ""

    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip(" -.")
    name = re.sub(r"\s*\([^)]*$", "", name).strip(" -.")
    name = re.sub(r"^(?:chair|judge|member|signed)\s*:\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+-\s*$", "", name).strip(" -.")
    name = _strip_judge_suffix_tokens(name)
    aliased_name = JUDGE_NAME_ALIASES.get(_person_key(name))
    if aliased_name:
        return aliased_name
    if (
        len(name) > 60
        or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", name)
        or _is_fragment_judge_name(name)
    ):
        return ""
    return name


def _strip_judge_suffix_tokens(name: str) -> str:
    tokens = name.split()
    while len(tokens) > 2 and tokens[-1].strip(".,").upper() in JUDGE_SUFFIX_TERMS:
        tokens.pop()
    return " ".join(tokens).strip(" -.")


def _is_fragment_judge_name(name: str) -> bool:
    tokens = name.split()
    if len(tokens) < 2:
        return True
    if all(not any(char.islower() for char in token) for token in tokens):
        return True
    return all(token.strip(".,").upper() in JUDGE_SUFFIX_TERMS for token in tokens)


def _person_key(value: str) -> str:
    normalized = _as_text(value).replace("ß", "ss")
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", normalized.casefold())


def _review_flags(
    *,
    raw_request_type: str,
    request_type: str,
    raw_rules: list[str],
    normalized_rules: list[str],
    raw_judges: list[str],
    normalized_judges: list[str],
) -> list[str]:
    flags: list[str] = []
    if not raw_request_type:
        flags.append("Missing type")
    elif "event:" in raw_request_type.casefold() or "race number:" in raw_request_type.casefold():
        flags.append("Type contains header text")
    elif _request_type_key(request_type) not in {
        _request_type_key(canonical_type) for canonical_type in CANONICAL_REQUEST_TYPES
    }:
        flags.append("Nonstandard type")

    noisy_rules = [rule for rule in raw_rules if _rule_needs_review(rule)]
    if noisy_rules:
        flags.append("Rules cleaned")
    if raw_rules and not normalized_rules:
        flags.append("Rules missing")

    if any(raw_judges) and not normalized_judges:
        flags.append("Jury names missing")
    elif len(_as_list(raw_judges)) != len(normalized_judges):
        flags.append("Jury names cleaned")
    return flags


def _rule_needs_review(rule: str) -> bool:
    normalized = _extract_rule_labels(rule)
    return (
        len(rule) > 80
        or any(pattern in rule.casefold() for pattern in NOISY_RULE_PATTERNS)
        or bool(rule and not normalized)
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            unique_values.append(value)
    return unique_values


def _dedupe_by_key(values: list[str], key_func: Any) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        key = key_func(value)
        if value and key and key not in seen:
            seen.add(key)
            unique_values.append(value)
    return unique_values


def _make_id(relative_path: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", relative_path.casefold()).strip("-")
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:56]}-{digest}"


def _natural_key(value: str) -> list[int | str]:
    parts = re.split(r"(\d+)", value.casefold())
    return [int(part) if part.isdigit() else part for part in parts]


def _sorted_counter(values: Any) -> list[tuple[str, int]]:
    counts = Counter(value for value in values if value)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))


def _sorted_counter_by_key(values: Any) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    display_counts: dict[str, Counter[str]] = {}
    for value in values:
        if not value:
            continue
        key = _person_key(value)
        if not key:
            continue
        counts[key] += 1
        display_counts.setdefault(key, Counter())[value] += 1

    rows: list[tuple[str, int]] = []
    for key, count in counts.items():
        display = sorted(
            display_counts[key].items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )[0][0]
        rows.append((display, count))
    return sorted(rows, key=lambda item: (-item[1], item[0].casefold()))
