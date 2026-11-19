import json
from pathlib import Path
from typing import Any

from evals.generator.build import DOCUMENTS_DIR

EVALS_DIR = DOCUMENTS_DIR.parent
DOC_IDS = (
    [f"D{n:02}" for n in range(1, 21)]
    + [f"E{n:02}" for n in range(1, 11)]
    + [f"H{n:02}" for n in range(1, 13)]
)
PHOTO_IDS = {"E06", "E07", "E10"}
PDF_IDS = [doc_id for doc_id in DOC_IDS if doc_id not in PHOTO_IDS]


def document_path(doc_id: str) -> Path:
    return DOCUMENTS_DIR / f"{doc_id}{'.jpg' if doc_id in PHOTO_IDS else '.pdf'}"


def review_cases(name: str = "review_cases.json") -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads((EVALS_DIR / name).read_text("utf-8"))
    return cases
