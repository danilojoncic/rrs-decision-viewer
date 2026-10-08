from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "data" / "decisions"
DOCS_ASSETS_DIR = ROOT / "docs" / "assets"
OUTPUT_PATH = DOCS_ASSETS_DIR / "decisions-data.js"

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


def main() -> None:
    records, request_types = _load_records()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(records),
        "facets": {
            "events": _facet_rows(record["event"] for record in records),
            "request_types": _facet_rows(request_types),
            "rules": _facet_rows(
                (rule for record in records for rule in record["rules"]),
                key_func=_rule_key,
            ),
        },
        "decisions": records,
    }

    DOCS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    serialized = (
        serialized.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    OUTPUT_PATH.write_text(
        f"window.DECISION_VIEWER_DATA = {serialized};\n", encoding="utf-8"
    )
    print(f"Wrote {OUTPUT_PATH} with {len(records)} decisions.")
    build_standalone()


def _load_records() -> tuple[list[dict[str, object]], list[str]]:
    records: list[dict[str, object]] = []
    request_types: list[str] = []
    for path in CASES_DIR.rglob("*.json"):
        relative_path = path.relative_to(CASES_DIR)
        if any(part.startswith(".") for part in relative_path.parts):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = _text_list(data.get("rules"))
        request_type = _request_type(data.get("request_type"))
        if request_type:
            request_types.append(request_type)
        stable_path = f"base/{relative_path.as_posix()}"
        records.append(
            {
                "id": _make_id(stable_path),
                "origin_system": _text(data.get("origin_system")),
                "event": _text(data.get("event")),
                "type": request_type or "Decision",
                "filename": path.name,
                "hearing_datetime": _text(data.get("hearing_datetime")),
                "race_number": _text(data.get("race_number")),
                "parties": _text_list(data.get("parties")),
                "procedural_matters": _text_list(data.get("procedural_matters")),
                "facts": _text_list(data.get("facts")),
                "rules": rules,
                "conclusions": _text_list(data.get("conclusions")),
                "decision": _text_list(data.get("decision")),
                "rule_keys": [_rule_key(rule) for rule in rules],
            }
        )
    records.sort(
        key=lambda record: (
            _natural_key(str(record["event"])),
            _natural_key(str(record["race_number"])),
            str(record["filename"]).casefold(),
        )
    )
    return records, request_types


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _request_type(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if "event:" in text.casefold() and "race number:" in text.casefold():
        return "Decision"
    key = text.casefold().replace("&", " and ").replace("/", " and ")
    key = re.sub(r"[^a-z0-9]+", " ", key).strip()
    if key in REQUEST_TYPE_ALIASES:
        return REQUEST_TYPE_ALIASES[key]
    uppercase_words = {"PC", "RC", "TC"}
    words = []
    for word in text.split():
        letters = re.sub(r"[^A-Za-z]", "", word).upper()
        words.append(letters if letters in uppercase_words else word.capitalize())
    return " ".join(words)


def _rule_key(rule: str) -> str:
    folded = re.sub(r"^rrs\s*", "", rule.casefold())
    return re.sub(r"[^a-z0-9]+", "", folded)


def _make_id(relative_path: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", relative_path.casefold()).strip("-")
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:56]}-{digest}"


def _natural_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", value.casefold())
    ]


def _facet_rows(
    values: Any, *, key_func: Any | None = None
) -> list[dict[str, object]]:
    counts = Counter(value for value in values if value)
    rows = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    return [
        {"label": label, "key": key_func(label) if key_func else label, "count": count}
        for label, count in rows
    ]


def build_standalone() -> None:
    """Bundle runtime assets into one HTML file that also works via file://."""
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    css = (DOCS_ASSETS_DIR / "styles.css").read_text(encoding="utf-8")
    theme = (DOCS_ASSETS_DIR / "theme-init.js").read_text(encoding="utf-8")
    flag = base64.b64encode(
        (DOCS_ASSETS_DIR / "montenegro.svg").read_bytes()
    ).decode("ascii")
    html = html.replace(
        "./assets/montenegro.svg", "data:image/svg+xml;base64," + flag
    )
    data = OUTPUT_PATH.read_text(encoding="utf-8")
    app = (DOCS_ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="./assets/styles.css">',
        "<style>\n" + css + "\n</style>",
    )
    html = re.sub(
        r'\s*<meta http-equiv="Content-Security-Policy"[^>]+>', "", html
    )
    html = html.replace(
        '  <script src="./assets/theme-init.js"></script>\n',
        "<script>\n" + theme + "\n</script>\n",
    )
    html = html.replace(
        '  <script src="./assets/decisions-data.js" defer></script>\n', ""
    )
    html = html.replace('  <script src="./assets/app.js" defer></script>\n', "")
    html = html.replace(
        "</body>",
        "<script>\n" + data + "\n</script>\n<script>\n" + app + "\n</script>\n</body>",
    )
    output = ROOT / "Decision Viewer.html"
    output.write_text(html, encoding="utf-8")
    print(
        f"Wrote {output} ({output.stat().st_size / 1024 / 1024:.1f} MB), "
        "ready to open offline."
    )


if __name__ == "__main__":
    main()
