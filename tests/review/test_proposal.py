import uuid
from collections.abc import Collection, Sequence

import pytest
from pydantic import ValidationError

from app.review.models import Decision
from app.review.proposal import ReviewProposal, checked_proposal_model, normalize_quote
from tests.review.fakes import EXPENSE_CLAUSES, kb_clause, proposal_input

# as if the agent had retrieved every Expense Policy clause
CLAUSES = {clause_id: kb_clause(clause_id).clause_text or "" for clause_id in EXPENSE_CLAUSES}


def checked(
    decision: str = "approve",
    reasons: Sequence[tuple[str, str]] = (("2.1", "lunch EUR 25, dinner EUR 45"),),
    missing_information: Sequence[str] = (),
    duplicate_of: uuid.UUID | None = None,
    found: Collection[uuid.UUID] = (),
) -> ReviewProposal:
    model = checked_proposal_model(CLAUSES, found)
    return model.model_validate(
        proposal_input(decision, reasons, missing_information, duplicate_of)
    )


def test_only_clauses_retrieved_in_this_review_can_be_cited() -> None:
    model = checked_proposal_model({"2.1": CLAUSES["2.1"]}, ())
    cites_7_1 = proposal_input(
        "reject", [("7.1", "A claim that exceeds a limit in this policy is rejected as a whole")]
    )

    with pytest.raises(ValidationError, match=r"'7\.1' is not a binding clause retrieved"):
        model.model_validate(cites_7_1)


def test_the_document_line_of_a_kb_chunk_is_not_quotable() -> None:
    with pytest.raises(ValidationError, match="not verbatim"):
        checked(reasons=[("2.1", "Expense Policy: 2. Meals **2.1 Meals during")])


def test_a_verbatim_quote_is_accepted() -> None:
    proposal = checked(reasons=[("2.1", "lunch EUR 25, dinner EUR 45")])

    assert proposal.decision is Decision.APPROVE


def test_markdown_and_whitespace_are_ignored_but_case_is_not() -> None:
    assert checked(reasons=[("2.1", "**2.1 Meals during business trips.**  During a business")])
    with pytest.raises(ValidationError, match="not verbatim"):
        checked(reasons=[("2.1", "LUNCH EUR 25, DINNER EUR 45")])


def test_a_quote_from_another_clause_is_refused() -> None:
    with pytest.raises(ValidationError, match=r"reasons\[0\]: the quote is not verbatim in clause"):
        checked(reasons=[("2.2", "lunch EUR 25, dinner EUR 45")])


@pytest.mark.parametrize(
    ("clause_id", "quote"),
    [
        # contractor policy, verbatim there
        ("C2.2", "A meal with clients or partners is reimbursed"),
        # FAQ entry id
        ("FAQ-13", "lunch EUR 25, dinner EUR 45"),
        ("Expense Policy 2.1", "lunch EUR 25, dinner EUR 45"),
    ],
)
def test_other_documents_are_never_a_valid_source(clause_id: str, quote: str) -> None:
    with pytest.raises(ValidationError, match="is not a binding clause retrieved"):
        checked(reasons=[(clause_id, quote)])


def test_a_paraphrase_or_an_ellipsis_is_refused() -> None:
    with pytest.raises(ValidationError, match="not verbatim"):
        checked(reasons=[("2.1", "the dinner limit is EUR 45 per meal")])
    with pytest.raises(ValidationError, match="not verbatim"):
        checked(reasons=[("2.1", "breakfast EUR 15 ... dinner EUR 45")])


def test_a_quote_of_a_few_words_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least 4 words"):
        checked(reasons=[("2.1", "dinner EUR 45")])


def test_every_reason_is_checked() -> None:
    with pytest.raises(ValidationError) as error:
        checked(
            reasons=[
                ("2.1", "lunch EUR 25, dinner EUR 45"),
                ("7.1", "the claim is over the limit and rejected"),
            ]
        )

    assert "reasons[1]" in str(error.value)
    assert "reasons[0]" not in str(error.value)


def test_at_least_one_reason() -> None:
    with pytest.raises(ValidationError, match="reasons"):
        checked(reasons=[])


@pytest.mark.parametrize(
    ("decision", "missing"),
    [("needs_info", []), ("approve", ["The attendee list"]), ("reject", ["Anything"])],
)
def test_missing_information_exactly_when_needs_info(decision: str, missing: list[str]) -> None:
    with pytest.raises(ValidationError, match="missing_information"):
        checked(decision=decision, missing_information=missing)


def test_needs_info_with_what_is_missing() -> None:
    proposal = checked(
        decision="needs_info",
        reasons=[("7.2", "the reviewer asks for it instead of rejecting")],
        missing_information=["The names and companies of all attendees"],
    )

    assert proposal.missing_information == ["The names and companies of all attendees"]


def test_duplicate_of_must_come_from_find_duplicate_claims() -> None:
    earlier = uuid.uuid4()
    duplicate_reason = ("1.4", "the later claim is rejected")

    with pytest.raises(ValidationError, match="find_duplicate_claims returned"):
        checked(decision="reject", reasons=[duplicate_reason], duplicate_of=earlier)

    proposal = checked(
        decision="reject", reasons=[duplicate_reason], duplicate_of=earlier, found={earlier}
    )
    assert proposal.duplicate_of == earlier


def test_duplicate_of_needs_a_reason_citing_1_4() -> None:
    earlier = uuid.uuid4()

    with pytest.raises(ValidationError, match=r"citing clause 1\.4"):
        checked(decision="reject", duplicate_of=earlier, found={earlier})


def test_found_duplicates_are_read_when_the_proposal_is_validated() -> None:
    found: set[uuid.UUID] = set()
    model = checked_proposal_model(CLAUSES, found)
    earlier = uuid.uuid4()
    found.add(earlier)  # the tool ran after the model class was made

    proposal = model.model_validate(
        proposal_input("reject", [("1.4", "the later claim is rejected")], (), earlier)
    )

    assert proposal.duplicate_of == earlier


def test_the_checked_model_keeps_the_contract_name() -> None:
    model = checked_proposal_model(CLAUSES, set())

    assert model.__name__ == "ReviewProposal"
    assert issubclass(model, ReviewProposal)


def test_normalize_quote() -> None:
    assert normalize_quote("**0.5 Pre-approval reference.**  `PA-YYYY-NNN`\n issued") == (
        "0.5 Pre-approval reference. PA-YYYY-NNN issued"
    )
