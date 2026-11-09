from pathlib import Path

from app.extraction.pages import UnusableFileError, document_to_images
from app.extraction.schemas import ExtractedExpense
from evals.extraction.models import EvalDocument

DOCUMENTS_DIR = Path(__file__).resolve().parents[1] / "documents"
CONTENT_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg"}


def available_ids() -> list[str]:
    return sorted(path.stem for path in DOCUMENTS_DIR.iterdir() if path.suffix in CONTENT_TYPES)


def load_document(doc_id: str, max_pages: int) -> EvalDocument:
    candidates = (DOCUMENTS_DIR / f"{doc_id}{suffix}" for suffix in CONTENT_TYPES)
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"no document file for {doc_id} in {DOCUMENTS_DIR}")
    label_path = DOCUMENTS_DIR / f"{doc_id}.json"
    label = (
        ExtractedExpense.model_validate_json(label_path.read_text("utf-8"))
        if label_path.exists()
        else None
    )
    try:
        pages = document_to_images(path.read_bytes(), CONTENT_TYPES[path.suffix], max_pages)
    except UnusableFileError as exc:
        return EvalDocument(doc_id, label, unusable_reason=exc.reason)
    return EvalDocument(doc_id, label, pages)
