import re
import uuid
from collections.abc import Collection, Mapping
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.review.models import Decision

MIN_QUOTE_WORDS = 4
DUPLICATES_CLAUSE = "1.4"
MARKDOWN_MARKS = re.compile(r"[*`]")

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: Text = Field(description='Id of a binding clause you retrieved, e.g. "2.1"')
    quote: Text = Field(
        description="Copied character for character from that clause: one continuous passage"
    )
    explanation: Text = Field(description="One or two sentences applying the clause to this claim")


class ReviewProposal(BaseModel):
    """The proposed decision on the claim, with the binding policy clauses it relies on"""

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    reasons: list[Reason] = Field(min_length=1, description="One per clause relied on")
    missing_information: list[Text] = Field(
        description="What the employee must provide; non-empty only for needs_info"
    )
    duplicate_of: uuid.UUID | None = Field(
        description="claim_id from find_duplicate_claims when clause 1.4 applies, otherwise null"
    )

    @model_validator(mode="after")
    def _missing_information_iff_needs_info(self) -> Self:
        if (self.decision is Decision.NEEDS_INFO) != bool(self.missing_information):
            raise ValueError("missing_information must be non-empty exactly when needs_info")
        return self


def normalize_quote(text: str) -> str:
    return " ".join(MARKDOWN_MARKS.sub("", text).split())


def quote_errors(reasons: list[Reason], retrieved_clauses: Mapping[str, str]) -> list[str]:
    """Every quote is verbatim in a binding clause retrieved from the KB in this review"""
    errors = []
    for index, reason in enumerate(reasons):
        where = f"reasons[{index}]"
        text = retrieved_clauses.get(reason.clause_id)
        quote = normalize_quote(reason.quote)
        if text is None:
            errors.append(
                f"{where}: {reason.clause_id!r} is not a binding clause retrieved in this review; "
                "cite only clauses with binding: true, fetched with search_policy or get_clause"
            )
        elif len(quote.split()) < MIN_QUOTE_WORDS:
            errors.append(f"{where}: the quote must have at least {MIN_QUOTE_WORDS} words")
        elif quote not in normalize_quote(text):
            errors.append(
                f"{where}: the quote is not verbatim in clause {reason.clause_id}; copy one "
                "continuous passage of that clause exactly"
            )
    return errors


def duplicate_errors(proposal: ReviewProposal, found: Collection[uuid.UUID]) -> list[str]:
    if proposal.duplicate_of is None:
        return []
    errors = []
    if proposal.duplicate_of not in found:
        errors.append("duplicate_of must be a claim_id that find_duplicate_claims returned")
    if all(reason.clause_id != DUPLICATES_CLAUSE for reason in proposal.reasons):
        errors.append(f"duplicate_of needs a reason citing clause {DUPLICATES_CLAUSE}")
    return errors


def checked_proposal_model(
    retrieved_clauses: Mapping[str, str], found_duplicates: Collection[uuid.UUID]
) -> type[ReviewProposal]:
    """ReviewProposal that also checks the quotes and duplicate_of. Both arguments are read at
    validation time, so the tools can fill them while the agent runs."""

    class CheckedProposal(ReviewProposal):
        __doc__ = ReviewProposal.__doc__
        # Strands names the output tool after the class
        model_config = ConfigDict(title=ReviewProposal.__name__)

        @model_validator(mode="after")
        def _evidence_is_valid(self) -> Self:
            errors = quote_errors(self.reasons, retrieved_clauses)
            errors += duplicate_errors(self, found_duplicates)
            if errors:
                raise ValueError("; ".join(errors))
            return self

    CheckedProposal.__name__ = ReviewProposal.__name__
    return CheckedProposal
