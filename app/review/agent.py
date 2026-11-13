import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Iterable
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Protocol

from strands import Agent, tool
from strands.models.model import Model
from strands.types.content import SystemContentBlock
from strands.types.tools import ToolContext

from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import ClaimsHistory
from app.review.policy import PolicyChunk, PolicyRetriever
from app.review.prompts import (
    FIND_DUPLICATE_CLAIMS_TOOL,
    GET_CLAUSE_TOOL,
    GET_TRAINING_SPEND_TOOL,
    SEARCH_POLICY_TOOL,
    SYSTEM_PROMPT,
    claim_message,
)
from app.review.proposal import ReviewProposal, checked_proposal_model

logger = logging.getLogger(__name__)

TOOL_UNAVAILABLE = "The tool is unavailable; the review stops here."


@dataclass(frozen=True)
class ValidProposal:
    proposal: ReviewProposal
    retrieved_clauses: list[str]
    model: str


@dataclass(frozen=True)
class NoValidProposal:
    """`detail` is for the log"""

    detail: str


ReviewOutcome = ValidProposal | NoValidProposal


class ReviewAgent(Protocol):
    async def review(self, claim: ClaimUnderReview) -> ReviewOutcome: ...


class ToolFailedError(Exception):
    """A tool could not get its data (KB or database); the review is retried later"""


class StrandsReviewAgent:
    def __init__(
        self,
        model: Model,
        model_name: str,
        retriever: PolicyRetriever,
        history: ClaimsHistory,
        *,
        max_turns: int,
        max_proposal_attempts: int,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._retriever = retriever
        self._history = history
        self._limits = {"turns": max_turns, "structured_output_attempts": max_proposal_attempts}
        self._system_prompt: list[SystemContentBlock] = [
            {"text": SYSTEM_PROMPT},
            {"cachePoint": {"type": "default"}},  # cached by Bedrock
        ]

    async def review(self, claim: ClaimUnderReview) -> ReviewOutcome:
        run = ReviewRun(claim, self._retriever, self._history)
        agent = Agent(
            model=self._model,
            tools=run.tools(),
            system_prompt=self._system_prompt,
            callback_handler=None,
        )
        result = await agent.invoke_async(
            claim_message(claim),
            structured_output_model=checked_proposal_model(run.quotable_clauses, run.duplicate_ids),
            limits=self._limits,  # type: ignore[arg-type]
        )
        if run.failure is not None:
            raise ToolFailedError("a review tool failed") from run.failure
        if not isinstance(result.structured_output, ReviewProposal):
            return NoValidProposal(f"no valid proposal, stop reason {result.stop_reason}")
        return ValidProposal(
            result.structured_output, list(run.retrieved_clause_ids), self._model_name
        )


class ReviewRun:
    """The tools of one review, bound to its claim"""

    def __init__(
        self,
        claim: ClaimUnderReview,
        retriever: PolicyRetriever,
        history: ClaimsHistory,
    ) -> None:
        self._claim = claim
        self._retriever = retriever
        self._history = history
        # the clause ids in the order the agent first saw them
        self.retrieved_clause_ids: dict[str, None] = {}
        # binding clause texts retrieved so far: the only ones a quote may come from
        self.quotable_clauses: dict[str, str] = {}
        self.duplicate_ids: set[uuid.UUID] = set()
        self.failure: Exception | None = None

    def tools(self) -> list[Any]:
        @tool(name=SEARCH_POLICY_TOOL, context=True)
        async def search_policy(query: str, tool_context: ToolContext) -> str:
            """Search the expense policy documents. Returns the best matching clauses with the
            clauses they refer to; only binding clauses may be cited.

            Args:
                query: What to look for, described in the policy's words.
            """
            chunks = await self._lookup_or_stop(tool_context, self._retriever.search(query))
            if chunks is None:
                return TOOL_UNAVAILABLE
            self._log_found(f"{SEARCH_POLICY_TOOL}({query!r})", [c.clause_id for c in chunks])
            return self._chunks_json(chunks)

        @tool(name=GET_CLAUSE_TOOL, context=True)
        async def get_clause(clause_id: str, tool_context: ToolContext) -> str:
            """Get the full text of a binding clause by its id.

            Args:
                clause_id: The clause id, e.g. "7.1".
            """
            clause_id = clause_id.strip()
            found_chunk = await self._lookup_or_stop(
                tool_context, self._retriever.clause(clause_id)
            )
            if self.failure is not None:
                return TOOL_UNAVAILABLE
            found = found_chunk.clause_id if found_chunk else "nothing"
            self._log_found(f"{GET_CLAUSE_TOOL}({clause_id!r})", found)
            if found_chunk is None:
                return f"There is no binding clause {clause_id!r}."
            return self._chunks_json([found_chunk])

        @tool(name=FIND_DUPLICATE_CLAIMS_TOOL, context=True)
        async def find_duplicate_claims(tool_context: ToolContext) -> str:
            """Find earlier claims, from any employee, with the same document date, total and
            currency as this claim, or the same file (policy 1.4)."""
            found_claim_duplicates = await self._lookup_or_stop(
                tool_context, self._history.find_possible_duplicates(self._claim)
            )
            if found_claim_duplicates is None:
                return TOOL_UNAVAILABLE
            self._log_found(
                f"{FIND_DUPLICATE_CLAIMS_TOOL}()",
                [str(claim.claim_id) for claim in found_claim_duplicates],
            )
            self.duplicate_ids.update(claim.claim_id for claim in found_claim_duplicates)
            return _json(
                {"possible_duplicates": [asdict(claim) for claim in found_claim_duplicates]}
            )

        @tool(name=GET_TRAINING_SPEND_TOOL, context=True)
        async def get_training_spend(tool_context: ToolContext) -> str:
            """List the employee's earlier training claims (books, courses, exams) in the calendar
            year of this claim's document date, with their total (policy 5.1)."""
            claims = await self._lookup_or_stop(
                tool_context, self._history.list_training_claims(self._claim)
            )
            if claims is None:
                return TOOL_UNAVAILABLE
            totals: defaultdict[str, Decimal] = defaultdict(Decimal)
            for claim in claims:
                totals[claim.currency] += claim.total
            self._log_found(
                f"{GET_TRAINING_SPEND_TOOL}()",
                f"{len(claims)} claims, total "
                + (", ".join(f"{amount} {currency}" for currency, amount in totals.items()) or "0"),
            )
            return _json(
                {
                    "earlier_training_claims": [asdict(claim) for claim in claims],
                    "total_by_currency": totals,
                }
            )

        return [search_policy, get_clause, find_duplicate_claims, get_training_spend]

    def _log_found(self, tool_call: str, found: object) -> None:
        logger.info("claim %s: %s found %s", self._claim.claim_id, tool_call, found)

    async def _lookup_or_stop[T](self, tool_context: ToolContext, work: Awaitable[T]) -> T | None:
        """A failed lookup stops the run: deciding without the data would be guessing"""
        try:
            return await work
        except Exception as exc:
            logger.exception("review tool failed for claim %s", self._claim.claim_id)
            self.failure = exc
            tool_context.agent.cancel()
            return None

    def _chunks_json(self, chunks: Iterable[PolicyChunk]) -> str:
        found_chunks = []
        for chunk in chunks:
            if chunk.clause_id:
                self.retrieved_clause_ids[chunk.clause_id] = None
            if chunk.binding and (clause_text := chunk.clause_text):
                self.quotable_clauses[chunk.clause_id] = clause_text
            found_chunks.append(
                {
                    "clause_id": chunk.clause_id,
                    "document": chunk.document,
                    "binding": chunk.binding,
                    "text": chunk.text,
                    "references": list(chunk.references),
                }
            )
        return _json(found_chunks)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
