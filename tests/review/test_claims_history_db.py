from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.status import ClaimStatus as S
from app.extraction.models import ExpenseCategory
from app.review.claim_data import (
    ClaimUnderReview,
    load_claim_of_any_status,
    load_extracted_claim,
)
from app.review.claims_history import DatabaseClaimsHistory
from tests.review.db import extracted_claim

pytestmark = pytest.mark.integration


def history(db_session: AsyncSession) -> DatabaseClaimsHistory:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db_session

    return DatabaseClaimsHistory(sessions)


async def under_review(db_session: AsyncSession, case_id: str, **kwargs: Any) -> ClaimUnderReview:
    claim_id = await extracted_claim(db_session, case_id, **kwargs)
    claim = await load_extracted_claim(db_session, claim_id)
    assert claim is not None
    return claim


async def test_d17_finds_d01_of_the_same_vendor_date_and_total(db_session: AsyncSession) -> None:
    d01 = await extracted_claim(db_session, "D01", status=S.IN_REVIEW)
    d17 = await under_review(db_session, "D17")

    [found] = await history(db_session).find_possible_duplicates(d17)

    assert found.claim_id == d01
    assert found.vendor_name == "Brauhaus am Markt"
    assert found.total == Decimal("18.50")
    assert found.status == "in_review"
    assert found.same_employee
    assert not found.same_file


async def test_duplicates_of_another_employee_count(db_session: AsyncSession) -> None:
    """A receipt handed to a colleague is the same expense"""
    d01 = await extracted_claim(db_session, "D01", employee_sub="colleague", status=S.APPROVED)
    d17 = await under_review(db_session, "D17")

    [found] = await history(db_session).find_possible_duplicates(d17)

    assert found.claim_id == d01
    assert not found.same_employee


async def test_the_same_file_is_found_even_if_extracted_differently(
    db_session: AsyncSession,
) -> None:
    sha = "a" * 64
    earlier = await extracted_claim(db_session, "D01", sha256=sha, total=Decimal("18.00"))
    later = await under_review(db_session, "D17", sha256=sha)

    [found] = await history(db_session).find_possible_duplicates(later)

    assert found.claim_id == earlier
    assert found.same_file


async def test_only_claims_submitted_earlier_count(db_session: AsyncSession) -> None:
    """Policy 1.4: the later claim is rejected, never the earlier one"""
    d01 = await under_review(db_session, "D01")
    await extracted_claim(db_session, "D17")

    assert await history(db_session).find_possible_duplicates(d01) == []


async def test_failed_claims_are_not_prior_claims(db_session: AsyncSession) -> None:
    """After `failed` the employee is told to submit a new claim"""
    await extracted_claim(db_session, "D01", status=S.FAILED)
    d17 = await under_review(db_session, "D17")

    assert await history(db_session).find_possible_duplicates(d17) == []


@pytest.mark.parametrize(
    "change",
    [
        {"total": Decimal("18.49")},
        {"document_date": "2026-09-04"},
        {"currency": "CHF"},
    ],
)
async def test_a_different_total_date_or_currency_is_no_duplicate(
    db_session: AsyncSession, change: dict[str, Any]
) -> None:
    await extracted_claim(db_session, "D01", **change)
    d17 = await under_review(db_session, "D17")

    assert await history(db_session).find_possible_duplicates(d17) == []


async def test_training_claims_of_the_employee_in_the_documents_year(
    db_session: AsyncSession,
) -> None:
    d20 = await under_review(db_session, "D20")
    book = {"category": ExpenseCategory.TRAINING}
    submitted = d20.submitted_at - timedelta(days=30)

    counted = await extracted_claim(
        db_session, "D20", submitted_at=submitted, status=S.APPROVED, **book
    )
    pending = await extracted_claim(
        db_session, "D20", submitted_at=submitted, status=S.IN_REVIEW, **book
    )
    left_out: tuple[dict[str, Any], ...] = (
        {"employee_sub": "colleague", **book},
        {"status": S.REJECTED, **book},
        {"status": S.FAILED, **book},
        {"document_date": "2025-12-30", **book},
        {"category": ExpenseCategory.CONFERENCE},
    )
    for changes in left_out:
        await extracted_claim(db_session, "D20", submitted_at=submitted, **changes)

    claims = await history(db_session).list_training_claims(d20)

    assert {claim.claim_id for claim in claims} == {counted, pending}
    assert {claim.status for claim in claims} == {"approved", "in_review"}


async def test_a_reviewed_claim_loads_in_any_status_but_not_as_extracted(
    db_session: AsyncSession,
) -> None:
    claim_id = await extracted_claim(db_session, "D01", status=S.IN_REVIEW)

    assert await load_extracted_claim(db_session, claim_id) is None
    claim = await load_claim_of_any_status(db_session, claim_id)
    assert claim is not None
    assert claim.claim_id == claim_id
