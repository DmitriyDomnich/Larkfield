from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.extraction.pages import PageImage
from app.extraction.schemas import ExtractedExpense
from evals.extraction.pricing import ModelPrice

Outcome = Literal["extracted", "unreadable", "invalid", "unusable_file", "error"]
FAILED_WITH_REASON: frozenset[Outcome] = frozenset({"unreadable", "unusable_file"})


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 0

    def cost(self, price: ModelPrice) -> Decimal:
        return (
            self.input_tokens * price.input_per_mtok + self.output_tokens * price.output_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class EvalDocument:
    doc_id: str
    label: ExtractedExpense | None
    pages: list[PageImage] = field(default_factory=list)
    unusable_reason: str | None = None


@dataclass(frozen=True)
class DocumentResult:
    doc_id: str
    outcome: Outcome
    detail: str | None
    expense: ExtractedExpense | None
    fields: dict[str, bool] | None
    latency_s: float | None
    usage: TokenUsage

    @property
    def passed(self) -> bool:
        if self.fields is not None:
            return all(self.fields.values())
        return self.outcome in FAILED_WITH_REASON
