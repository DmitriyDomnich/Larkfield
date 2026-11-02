from pathlib import Path

from app.extraction.schemas import ExtractedExpense
from evals.generator.families import FAMILIES
from evals.generator.photo import to_photo
from evals.generator.render import RENDER

DOCUMENTS_DIR = Path(__file__).resolve().parents[1] / "documents"


def label_path(doc_id: str) -> Path:
    return DOCUMENTS_DIR / f"{doc_id}.json"


def load_label(doc_id: str) -> ExtractedExpense | None:
    path = label_path(doc_id)
    if not path.exists():
        return None
    return ExtractedExpense.model_validate_json(path.read_text(encoding="utf-8"))


def content(doc_id: str) -> ExtractedExpense:
    """What the document shows: its label, or the spec's own data when it has no label (E10)"""
    data = load_label(doc_id) or RENDER[doc_id].data
    if data is None:
        raise ValueError(f"{doc_id} has neither a label nor data in its RenderSpec")
    return data


def suffix(doc_id: str) -> str:
    return ".jpg" if RENDER[doc_id].photo else ".pdf"


def render_pdf(doc_id: str, expense: ExtractedExpense | None = None) -> bytes:
    spec = RENDER[doc_id]
    return FAMILIES[spec.family](expense or content(doc_id), spec)


def render(doc_id: str) -> bytes:
    pdf = render_pdf(doc_id)
    photo = RENDER[doc_id].photo
    return to_photo(pdf, photo) if photo else pdf


def write(doc_id: str) -> Path:
    path = DOCUMENTS_DIR / f"{doc_id}{suffix(doc_id)}"
    path.write_bytes(render(doc_id))
    return path
