from __future__ import annotations

import base64
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.decision_repository import (
    DecisionRepository,
    _rule_key,
)


DOCS_ASSETS_DIR = ROOT / "docs" / "assets"
OUTPUT_PATH = DOCS_ASSETS_DIR / "decisions-data.js"


def main() -> None:
    repository = DecisionRepository(ROOT / "data" / "decisions", ROOT / "data" / "imports")
    records = repository.all()
    facets = repository.facets()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(records),
        "facets": {
            "events": _facet_rows(facets["events"]),
            "request_types": _facet_rows(facets["request_types"]),
            "rules": _facet_rows(facets["rules"], key_func=_rule_key),
        },
        "decisions": [_decision_row(record) for record in records],
    }

    DOCS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "window.DECISION_VIEWER_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH} with {len(records)} decisions.")
    build_standalone()


def build_standalone() -> None:
    """Bundle all runtime assets into one HTML file that also works via file://."""
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    css = (DOCS_ASSETS_DIR / "styles.css").read_text(encoding="utf-8")
    flag = base64.b64encode((DOCS_ASSETS_DIR / "montenegro.svg").read_bytes()).decode("ascii")
    html = html.replace("./assets/montenegro.svg", "data:image/svg+xml;base64," + flag)
    data = OUTPUT_PATH.read_text(encoding="utf-8")
    app = (DOCS_ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    # Imported text must never be able to close an inline script element.
    data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = html.replace('<link rel="stylesheet" href="./assets/styles.css">', "<style>\n" + css + "\n</style>")
    html = html.replace('  <script src="./assets/decisions-data.js" defer></script>\n', "")
    html = html.replace('  <script src="./assets/app.js" defer></script>\n', "")
    html = html.replace("</body>", "<script>\n" + data + "\n</script>\n<script>\n" + app + "\n</script>\n</body>")
    output = ROOT / "Decision Viewer.html"
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output} ({output.stat().st_size / 1024 / 1024:.1f} MB), ready to open offline.")


def _facet_rows(
    rows: list[tuple[str, int]],
    *,
    key_func: Any | None = None,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for label, count in rows:
        key = key_func(label) if key_func else label
        result.append({"label": label, "key": key, "count": count})
    return result


def _decision_row(record: Any) -> dict[str, object]:
    fields_for_search = [
        record.event,
        record.hearing_datetime,
        record.race_number,
        record.request_type,
        *record.parties,
        *record.procedural_matters,
        *record.facts,
        *record.rules,
        *record.conclusions,
        *record.decision,
        record.filename,
    ]

    return {
        "id": record.id,
        "origin_system": record.origin_system,
        "event": record.event,
        "type": record.request_type or "Decision",
        "filename": record.filename,
        "hearing_datetime": record.hearing_datetime,
        "race_number": record.race_number,
        "parties": record.parties,
        "procedural_matters": record.procedural_matters,
        "facts": record.facts,
        "rules": record.rules,
        "conclusions": record.conclusions,
        "decision": record.decision,
        "rule_keys": record.rule_keys,
        "review_flags": record.review_flags,
        "needs_review": record.needs_review,
        "search_text": _search_text(fields_for_search),
    }


def _search_text(values: list[Any]) -> str:
    return " ".join(_search_key(value) for value in values if _search_key(value))


def _search_key(value: Any) -> str:
    text = " ".join(str(value or "").split()).replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


if __name__ == "__main__":
    main()
