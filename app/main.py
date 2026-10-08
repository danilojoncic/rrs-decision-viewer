from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware

from app.config import (
    get_casebook_data_path,
    get_decisions_dir,
    get_imports_dir,
    get_rules_json_path,
    get_wording_xlsx_path,
)
from app.services.appendix_n_repository import (
    AppendixNRepository,
    AppendixNScenario,
    SimulatorResult,
)
from app.services.casebook_repository import CasebookCase, CasebookRepository
from app.services.decision_repository import DecisionRepository, DecisionRecord
from app.services.wording_repository import WordingEntry, WordingRepository


class CachedStaticFiles(StaticFiles):
    def __init__(self, *args: object, cache_control: str, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    async def get_response(self, path: str, scope: dict[str, object]) -> object:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.setdefault("Cache-Control", self.cache_control)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> object:
    _warm_repositories()
    yield


app = FastAPI(title="Judging Learning Platform", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
BASE_DIR = Path(__file__).resolve().parent
app.mount(
    "/static",
    CachedStaticFiles(
        directory=BASE_DIR / "static",
        cache_control="public, max-age=300, stale-while-revalidate=3600",
    ),
    name="static",
)

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@lru_cache
def get_repository() -> DecisionRepository:
    return DecisionRepository(get_decisions_dir(), get_imports_dir())


@lru_cache
def get_casebook_repository() -> CasebookRepository:
    return CasebookRepository(get_casebook_data_path())


@lru_cache
def get_appendix_n_repository() -> AppendixNRepository:
    return AppendixNRepository(get_rules_json_path())


@lru_cache
def get_wording_repository() -> WordingRepository:
    return WordingRepository(get_wording_xlsx_path())


def _warm_repositories() -> None:
    decision_repository = get_repository()
    decision_repository.all()
    decision_repository.facets()

    casebook_repository = get_casebook_repository()
    casebook_repository.all()
    casebook_repository.facets()

    appendix_repository = get_appendix_n_repository()
    appendix_repository.rules()

    wording_repository = get_wording_repository()
    wording_repository.all()
    wording_repository.facets()


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    event: str = "",
    request_type: str = "",
    origin_system: str = "",
    rules: Annotated[list[str] | None, Query()] = None,
    needs_review: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=20, le=100)] = 40,
) -> HTMLResponse:
    repository = get_repository()
    selected_request_type = repository.canonical_request_type_filter(request_type)
    selected_rules = repository.canonical_rule_filters(rules or [])
    results = repository.search(
        q=q,
        event=event,
        request_type=selected_request_type,
        origin_system=origin_system,
        rules=list(selected_rules),
        needs_review=needs_review,
    )
    result_count = len(results)
    page_count = max(1, ceil(result_count / per_page))
    current_page = min(page, page_count)
    start_index = (current_page - 1) * per_page
    end_index = min(start_index + per_page, result_count)
    paginated_results = results[start_index:end_index]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "data_dir": repository.data_dir,
            "imports_dir": repository.imports_dir,
            "facets": repository.facets(),
            "results": paginated_results,
            "result_count": result_count,
            "total_count": len(repository.all()),
            "review_count": repository.review_count(),
            "q": q,
            "selected_event": event,
            "selected_request_type": selected_request_type,
            "selected_origin_system": origin_system,
            "selected_rules": selected_rules,
            "selected_needs_review": needs_review,
            "page": current_page,
            "per_page": per_page,
            "page_count": page_count,
            "start_index": start_index + 1 if result_count else 0,
            "end_index": end_index,
            "page_url": lambda page_number: _page_url(request, page_number),
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/casebook", response_class=HTMLResponse)
def casebook_index(
    request: Request,
    q: str = "",
    rules: Annotated[list[str] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=20, le=100)] = 40,
) -> HTMLResponse:
    repository = get_casebook_repository()
    selected_rules = repository.canonical_rule_filters(rules or [])
    results = repository.search(q=q, rules=list(selected_rules))
    result_count = len(results)
    page_count = max(1, ceil(result_count / per_page))
    current_page = min(page, page_count)
    start_index = (current_page - 1) * per_page
    end_index = min(start_index + per_page, result_count)
    paginated_results = results[start_index:end_index]

    return templates.TemplateResponse(
        request,
        "casebook/index.html",
        {
            "casebook_title": repository.title,
            "facets": repository.facets(),
            "results": paginated_results,
            "result_count": result_count,
            "total_count": len(repository.all()),
            "q": q,
            "selected_rules": selected_rules,
            "page": current_page,
            "per_page": per_page,
            "page_count": page_count,
            "start_index": start_index + 1 if result_count else 0,
            "end_index": end_index,
            "page_url": lambda page_number: _page_url(request, page_number),
        },
    )


@app.get("/appendix-n", response_class=HTMLResponse)
def appendix_n_simulator(request: Request) -> HTMLResponse:
    repository = get_appendix_n_repository()
    scenario = _appendix_n_scenario_from_query(request)
    result = repository.evaluate(scenario)
    active_rules = [
        rule
        for number in result.active_rule_numbers
        if (rule := repository.rule(number)) is not None
    ]

    return templates.TemplateResponse(
        request,
        "appendix_n/index.html",
        {
            "scenario": scenario,
            "result": result,
            "rules": repository.rules(),
            "active_rules": active_rules,
            "presets": repository.presets(),
        },
    )


@app.get("/wording", response_class=HTMLResponse)
def wording_index(
    request: Request,
    q: str = "",
    sheet: str = "",
    kind: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=20, le=120)] = 60,
) -> HTMLResponse:
    repository = get_wording_repository()
    results = repository.search(q=q, sheet=sheet, kind=kind)
    result_count = len(results)
    page_count = max(1, ceil(result_count / per_page))
    current_page = min(page, page_count)
    start_index = (current_page - 1) * per_page
    end_index = min(start_index + per_page, result_count)
    paginated_results = results[start_index:end_index]

    return templates.TemplateResponse(
        request,
        "wording/index.html",
        {
            "facets": repository.facets(),
            "results": paginated_results,
            "result_count": result_count,
            "total_count": len(repository.all()),
            "q": q,
            "selected_sheet": sheet,
            "selected_kind": kind,
            "page": current_page,
            "per_page": per_page,
            "page_count": page_count,
            "start_index": start_index + 1 if result_count else 0,
            "end_index": end_index,
            "page_url": lambda page_number: _page_url(request, page_number),
            "topic_url": lambda selected_sheet: _wording_filter_url(
                request,
                q=q,
                sheet=selected_sheet,
                kind=kind,
            ),
        },
    )


@app.get("/casebook/{case_id}", response_class=HTMLResponse)
def casebook_detail(request: Request, case_id: str, focus: bool = False) -> HTMLResponse:
    repository = get_casebook_repository()
    case = repository.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Casebook case not found")

    previous_case, next_case = repository.neighbors(case_id)
    return templates.TemplateResponse(
        request,
        "casebook/detail.html",
        {
            "case": case,
            "previous_case": previous_case,
            "next_case": next_case,
            "casebook_title": repository.title,
            "focus_mode": focus,
        },
    )


@app.get("/decisions/{decision_id}", response_class=HTMLResponse)
def decision_detail(request: Request, decision_id: str, focus: bool = False) -> HTMLResponse:
    repository = get_repository()
    record = repository.get(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    previous_record, next_record = repository.neighbors(decision_id)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "record": record,
            "previous_record": previous_record,
            "next_record": next_record,
            "raw_json": json.dumps(_decision_data(record), ensure_ascii=False, indent=2),
            "focus_mode": focus,
        },
    )


@app.get("/api/casebook")
def api_casebook(
    q: str = "",
    rules: Annotated[list[str] | None, Query()] = None,
) -> dict[str, object]:
    repository = get_casebook_repository()
    selected_rules = repository.canonical_rule_filters(rules or [])
    results = repository.search(q=q, rules=list(selected_rules))
    return {
        "count": len(results),
        "total": len(repository.all()),
        "cases": [_casebook_summary(case) for case in results],
    }


@app.get("/api/casebook/{case_id}")
def api_casebook_detail(case_id: str) -> dict[str, object]:
    repository = get_casebook_repository()
    case = repository.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Casebook case not found")
    return {"case": _casebook_data(case)}


@app.get("/api/wording")
def api_wording(
    q: str = "",
    sheet: str = "",
    kind: str = "",
) -> dict[str, object]:
    repository = get_wording_repository()
    results = repository.search(q=q, sheet=sheet, kind=kind)
    return {
        "count": len(results),
        "total": len(repository.all()),
        "wording": [_wording_summary(entry) for entry in results],
    }


@app.get("/api/appendix-n/evaluate")
def api_appendix_n_evaluate(request: Request) -> dict[str, object]:
    repository = get_appendix_n_repository()
    scenario = _appendix_n_scenario_from_query(request)
    result = repository.evaluate(scenario)
    return {
        "scenario": scenario.__dict__,
        "result": _appendix_n_result_data(result),
        "active_rules": [
            {
                "number": rule.number,
                "title": rule.title,
                "text": rule.text,
                "section": rule.section,
            }
            for number in result.active_rule_numbers
            if (rule := repository.rule(number)) is not None
        ],
    }


@app.get("/api/decisions")
def api_decisions(
    q: str = "",
    event: str = "",
    request_type: str = "",
    origin_system: str = "",
    rules: Annotated[list[str] | None, Query()] = None,
    needs_review: bool = False,
) -> dict[str, object]:
    repository = get_repository()
    results = repository.search(
        q=q,
        event=event,
        request_type=request_type,
        origin_system=origin_system,
        rules=rules or [],
        needs_review=needs_review,
    )
    return {
        "count": len(results),
        "total": len(repository.all()),
        "decisions": [_decision_summary(record) for record in results],
    }


@app.get("/api/decisions/{decision_id}")
def api_decision_detail(decision_id: str) -> dict[str, object]:
    repository = get_repository()
    record = repository.get(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return {
        "id": record.id,
        "filename": record.filename,
        "source_path": record.source_path,
        "data": _decision_data(record),
        "review_flags": record.review_flags,
    }


def _wording_summary(entry: WordingEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "sheet": entry.sheet,
        "label": entry.label,
        "kind": entry.kind,
        "wording": entry.wording,
        "row_number": entry.row_number,
        "placeholders": entry.placeholders,
        "rules": entry.rules,
    }


def _appendix_n_scenario_from_query(request: Request) -> AppendixNScenario:
    return AppendixNScenario(
        body=_query_choice(
            request,
            "body",
            "full_jury",
            {"full_jury", "panel", "emergency", "recusal", "world_sailing_three"},
        ),
        matter=_query_choice(
            request,
            "matter",
            "part5",
            {"part5", "eligibility", "substitution", "referred", "advisory", "misconduct"},
        ),
        event_group=_query_choice(request, "event_group", "standard", {"standard", "mnq"}),
        members=_query_int(request, "members", 5, 1, 12),
        international_judges=_query_int(request, "international_judges", 3, 0, 12),
        national_authorities=_query_int(request, "national_authorities", 5, 1, 12),
        max_same_authority=_query_int(request, "max_same_authority", 1, 1, 12),
        independent=_query_bool(request, "independent", True),
        appointed=_query_bool(request, "appointed", True),
        na_approval_required=_query_bool(request, "na_approval_required", False),
        na_notice_posted=_query_bool(request, "na_notice_posted", True),
        illness_emergency=_query_bool(request, "illness_emergency", False),
        no_replacements=_query_bool(request, "no_replacements", False),
        ws_authorized=_query_bool(request, "ws_authorized", False),
        ws_letter_posted=_query_bool(request, "ws_letter_posted", False),
        oa_directs_otherwise=_query_bool(request, "oa_directs_otherwise", False),
        party_dissatisfied=_query_bool(request, "party_dissatisfied", False),
        facts_only=_query_bool(request, "facts_only", False),
        review_requested_in_time=_query_bool(request, "review_requested_in_time", False),
        review_panel_compliant=_query_bool(request, "review_panel_compliant", False),
        panel_failed_to_agree=_query_bool(request, "panel_failed_to_agree", False),
        chair_referred_deadlock=_query_bool(request, "chair_referred_deadlock", False),
        conflict_mode=_query_choice(
            request,
            "conflict_mode",
            "none",
            {"none", "nationality", "doubt", "significant"},
        ),
        presenter_in_panel=_query_bool(request, "presenter_in_panel", False),
        presenter_in_jury=_query_bool(request, "presenter_in_jury", False),
        materials_disclosed=_query_bool(request, "materials_disclosed", True),
        panel_investigated_before_hearing=_query_bool(
            request,
            "panel_investigated_before_hearing",
            False,
        ),
        ethics_procedure_applies=_query_bool(request, "ethics_procedure_applies", False),
    )


def _appendix_n_result_data(result: SimulatorResult) -> dict[str, object]:
    return {
        "verdict": result.verdict,
        "tone": result.tone,
        "hearing_scope": result.hearing_scope,
        "constitution_label": result.constitution_label,
        "findings": [
            {
                "severity": finding.severity,
                "title": finding.title,
                "detail": finding.detail,
                "rules": finding.rules,
            }
            for finding in result.findings
        ],
        "next_actions": result.next_actions,
        "active_rule_numbers": result.active_rule_numbers,
    }


def _casebook_summary(case: CasebookCase) -> dict[str, object]:
    return {
        "id": case.id,
        "case_number": case.case_number,
        "title": case.title,
        "rules": case.rules,
        "summary": case.summary,
        "sections": [section.title for section in case.sections],
    }


def _casebook_data(case: CasebookCase) -> dict[str, object]:
    return {
        "id": case.id,
        "case_number": case.case_number,
        "title": case.title,
        "status": case.status,
        "rules": case.rules,
        "summary": case.summary,
        "sections": [
            {"key": section.key, "title": section.title, "items": section.items}
            for section in case.sections
        ],
    }


def _decision_summary(record: DecisionRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "filename": record.filename,
        "event": record.event,
        "request_type": record.request_type,
        "race_number": record.race_number,
        "hearing_datetime": record.hearing_datetime,
        "parties": record.parties,
        "rules": record.rules,
        "review_flags": record.review_flags,
        "needs_review": record.needs_review,
    }


def _decision_data(record: DecisionRecord) -> dict[str, object]:
    return {
        "origin_system": record.origin_system,
        "request_type": record.request_type,
        "event": record.event,
        "race_number": record.race_number,
        "hearing_datetime": record.hearing_datetime,
        "parties": record.parties,
        "procedural_matters": record.procedural_matters,
        "facts": record.facts,
        "rules": record.rules,
        "conclusions": record.conclusions,
        "decision": record.decision,
    }


def _query_bool(request: Request, name: str, default: bool) -> bool:
    values = request.query_params.getlist(name)
    if not values:
        return default
    return values[-1].casefold() in {"1", "true", "yes", "on"}


def _query_int(
    request: Request,
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = request.query_params.get(name)
    if value is None:
        return default
    try:
        number = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, number))


def _query_choice(
    request: Request,
    name: str,
    default: str,
    choices: set[str],
) -> str:
    value = request.query_params.get(name, default)
    if value in choices:
        return value
    return default


def _page_url(request: Request, page_number: int) -> str:
    query_items = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key != "page"
    ]
    query_items.append(("page", str(page_number)))
    return f"{request.url.path}?{urlencode(query_items)}"


def _wording_filter_url(request: Request, *, q: str, sheet: str, kind: str) -> str:
    query_items = [
        (key, value)
        for key, value in [("q", q), ("sheet", sheet), ("kind", kind)]
        if value
    ]
    if not query_items:
        return str(request.url_for("wording_index"))
    return f"{request.url_for('wording_index')}?{urlencode(query_items)}"


