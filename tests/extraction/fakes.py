from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.extraction.extractor import ExtractionOutcome
from app.extraction.pages import PageImage
from app.extraction.queue import UploadMessage
from app.extraction.schemas import ExtractedExpense

DOCUMENTS = Path("evals/documents")


def label(document_id: str) -> dict[str, Any]:
    """The expected extraction of an evaluation document, as JSON"""
    expense = ExtractedExpense.model_validate_json((DOCUMENTS / f"{document_id}.json").read_text())
    return expense.model_dump(mode="json")


def expense(document_id: str, **changes: Any) -> ExtractedExpense:
    return ExtractedExpense.model_validate(label(document_id) | changes)


def document_bytes(name: str) -> bytes:
    return (DOCUMENTS / name).read_bytes()


class FakeExtractor:
    def __init__(self, *outcomes: ExtractionOutcome | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[Sequence[PageImage]] = []

    async def extract_expense(self, pages: Sequence[PageImage]) -> ExtractionOutcome:
        self.calls.append(pages)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeQueue:
    def __init__(self, *messages: UploadMessage) -> None:
        self.messages = list(messages)
        self.deleted: list[str] = []

    async def receive_messages(self) -> list[UploadMessage]:
        received, self.messages = self.messages, []
        return received

    async def delete_message(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)
