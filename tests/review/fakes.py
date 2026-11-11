import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from strands.models.model import Model
from strands.types.content import ContentBlockStart, Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

from app.review.agent import ReviewOutcome
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim
from app.review.policy import PolicyChunk
from app.review.queue import ReviewMessage
from evals.retrieval.clause_files import clause_file_text
from evals.retrieval.clauses import KB_DIR, parse_clauses
from tests.extraction.fakes import expense

REVIEW_CASES = Path("evals/review_cases.json")
EXPENSE_POLICY = "expense-policy"
EXPENSE_CLAUSES = {
    clause.clause_id: clause
    for clause in parse_clauses((KB_DIR / "expense-policy.md").read_text("utf-8"), EXPENSE_POLICY)
}


def kb_clause(clause_id: str, *references: str) -> PolicyChunk:
    """An Expense Policy clause as the `clause` KB returns it (the file `make kb-build` writes)"""
    clause = EXPENSE_CLAUSES[clause_id]
    return PolicyChunk(
        clause_id, EXPENSE_POLICY, clause_file_text(clause), references, binding=True
    )


def review_case(case_id: str) -> dict[str, Any]:
    cases: list[dict[str, Any]] = json.loads(REVIEW_CASES.read_text("utf-8"))
    return next(case for case in cases if case["id"] == case_id)


def claim_for_case(case_id: str, **changes: Any) -> ClaimUnderReview:
    """An extracted claim built from a review case and its document's label"""
    case = review_case(case_id)
    submitted = date.fromisoformat(case["submitted_at"])
    fields: dict[str, Any] = {
        "claim_id": uuid.uuid4(),
        "employee_sub": "employee-1",
        "purpose": case["claim"]["purpose"],
        "attendees": case["claim"]["attendees"],
        "preapproval_ref": case["claim"]["preapproval_ref"],
        "submitted_at": datetime.combine(submitted, time(9), UTC),
        "expense": expense(case_id),
    }
    return ClaimUnderReview(**(fields | changes))


def proposal_input(
    decision: str = "approve",
    reasons: Sequence[tuple[str, str]] = (("2.1", "lunch EUR 25, dinner EUR 45"),),
    missing_information: Sequence[str] = (),
    duplicate_of: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reasons": [
            {"clause_id": clause_id, "quote": quote, "explanation": "Applies to this claim."}
            for clause_id, quote in reasons
        ],
        "missing_information": list(missing_information),
        "duplicate_of": str(duplicate_of) if duplicate_of else None,
    }


Turn = str | tuple[str, dict[str, Any]]


@dataclass
class ModelCall:
    messages: Messages
    tool_names: list[str]
    tool_choice: Any
    system_prompt: str | None


class ScriptedModel(Model):
    """A Strands model that answers with preset turns: text, or (tool name, tool input)"""

    def __init__(self, *turns: Turn) -> None:
        self.turns = list(turns)
        self.calls: list[ModelCall] = []

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> dict[str, Any]:
        return {}

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any]]:
        raise NotImplementedError
        yield {}

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        self.calls.append(
            ModelCall(
                messages=json.loads(json.dumps(messages, default=str)),
                tool_names=[spec["name"] for spec in tool_specs or []],
                tool_choice=kwargs.get("tool_choice"),
                system_prompt=system_prompt,
            )
        )
        if not self.turns:
            raise AssertionError("the model was called more often than scripted")
        turn = self.turns.pop(0)
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(turn, str):
            yield {"contentBlockDelta": {"delta": {"text": turn}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        else:
            name, tool_input = turn
            tool_use_id = f"tool-{len(self.calls)}"
            start: ContentBlockStart = {"toolUse": {"toolUseId": tool_use_id, "name": name}}
            yield {"contentBlockStart": {"start": start}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                "metrics": {"latencyMs": 1},
            }
        }

    def tool_results(self) -> list[str]:
        """The text of every tool result the model was sent, in order"""
        last = self.calls[-1].messages if self.calls else []
        return [
            content["toolResult"]["content"][0]["text"]
            for message in last
            for content in message["content"]
            if "toolResult" in content
        ]


@dataclass
class FakeRetriever:
    """Search returns `results`; a clause by id comes from the Expense Policy file"""

    results: list[PolicyChunk] = field(default_factory=list)
    error: Exception | None = None
    queries: list[str] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)

    async def search(self, query: str) -> list[PolicyChunk]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.results

    async def clause(self, clause_id: str) -> PolicyChunk | None:
        self.clause_ids.append(clause_id)
        if self.error is not None:
            raise self.error
        return kb_clause(clause_id) if clause_id in EXPENSE_CLAUSES else None


@dataclass
class FakeHistory:
    duplicates: list[PossibleClaimDuplicate] = field(default_factory=list)
    training: list[TrainingClaim] = field(default_factory=list)
    error: Exception | None = None

    async def find_possible_duplicates(
        self, claim: ClaimUnderReview
    ) -> list[PossibleClaimDuplicate]:
        if self.error is not None:
            raise self.error
        return self.duplicates

    async def list_training_claims(self, claim: ClaimUnderReview) -> list[TrainingClaim]:
        if self.error is not None:
            raise self.error
        return self.training


class FakeAgent:
    def __init__(self, *outcomes: ReviewOutcome | Exception) -> None:
        self.outcomes = list(outcomes)
        self.reviewed: list[ClaimUnderReview] = []

    async def review(self, claim: ClaimUnderReview) -> ReviewOutcome:
        self.reviewed.append(claim)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeReviewQueue:
    def __init__(self, *messages: ReviewMessage) -> None:
        self.messages = list(messages)
        self.deleted: list[str] = []
        self.requested: list[uuid.UUID] = []
        self.request_error: Exception | None = None

    async def request_review(self, claim_id: uuid.UUID) -> None:
        if self.request_error is not None:
            raise self.request_error
        self.requested.append(claim_id)

    async def receive_messages(self) -> list[ReviewMessage]:
        received, self.messages = self.messages, []
        return received

    async def delete_message(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)
