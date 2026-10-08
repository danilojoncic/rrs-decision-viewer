from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DECISIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "decisions"
DEFAULT_IMPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "imports"
DEFAULT_CASEBOOK_PDF = Path("/Users/danilo/Desktop/cases.pdf")
DEFAULT_CASEBOOK_DATA = (
    Path(__file__).resolve().parent.parent / "data" / "casebook" / "world_sailing_cases.json"
)
DEFAULT_RULES_JSON = Path("/Users/danilo/Desktop/rrs json/rules.json")
DEFAULT_WORDING_XLSX = Path("/Users/danilo/Desktop/wording.xlsx")


def get_decisions_dir() -> Path:
    configured_dir = os.getenv("DECISIONS_JSON_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser()
    return DEFAULT_DECISIONS_DIR


def get_imports_dir() -> Path:
    configured_dir = os.getenv("DECISIONS_IMPORT_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser()
    return DEFAULT_IMPORTS_DIR


def get_casebook_pdf_path() -> Path:
    configured_path = os.getenv("CASEBOOK_PDF_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_CASEBOOK_PDF


def get_casebook_data_path() -> Path:
    configured_path = os.getenv("CASEBOOK_DATA_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_CASEBOOK_DATA


def get_rules_json_path() -> Path:
    configured_path = os.getenv("RRS_RULES_JSON_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_RULES_JSON


def get_wording_xlsx_path() -> Path:
    configured_path = os.getenv("WORDING_XLSX_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_WORDING_XLSX
