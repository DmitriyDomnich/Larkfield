"""Integration tests: need a real PostgreSQL at DATABASE_URL (CI service / docker compose)."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.models import Claim, ClaimStatusTransition
from app.claims.service import InvalidTransitionError, transition
from app.claims.status import ClaimStatus as S

pytestmark = pytest.mark.integration

ALLOWED = [
    (S.PENDING_UPLOAD, S.UPLOADED),
    (S.PENDING_UPLOAD, S.FAILED),
    (S.UPLOADED, S.EXTRACTING),
    (S.EXTRACTING, S.EXTRACTED),
    (S.EXTRACTING, S.FAILED),
    (S.EXTRACTED, S.IN_REVIEW),
    (S.EXTRACTED, S.FAILED),
    (S.IN_REVIEW, S.APPROVED),
    (S.IN_REVIEW, S.REJECTED),
    (S.IN_REVIEW, S.NEEDS_INFO),
    (S.NEEDS_INFO, S.EXTRACTED),
]

PATH = [S.UPLOADED, S.EXTRACTING, S.EXTRACTED, S.IN_REVIEW, S.NEEDS_INFO]


async def new_claim(session: AsyncSession, status: S = S.PENDING_UPLOAD) -> uuid.UUID:
    """Insert a claim and move it to `status` through allowed transitions."""
    claim = Claim(employee_sub="employee-1", purpose="Lunch during client workshop")
    session.add(claim)
    await session.flush()
    if status is not S.PENDING_UPLOAD:
        for step in PATH[: PATH.index(status) + 1]:
            await transition(session, claim.id, step)
    return claim.id


async def status_of(session: AsyncSession, claim_id: uuid.UUID) -> S:
    status = await session.scalar(select(Claim.status).where(Claim.id == claim_id))
    assert status is not None
    return status


@pytest.mark.parametrize(("current", "target"), ALLOWED)
async def test_allowed_transition(db_session: AsyncSession, current: S, target: S) -> None:
    claim_id = await new_claim(db_session, current)
    reason = "unreadable photo" if target is S.FAILED else None

    await transition(db_session, claim_id, target, failure_reason=reason)

    assert await status_of(db_session, claim_id) is target


async def test_refused_transition_through_service(db_session: AsyncSession) -> None:
    claim_id = await new_claim(db_session, S.UPLOADED)

    with pytest.raises(InvalidTransitionError):
        await transition(db_session, claim_id, S.APPROVED)

    assert await status_of(db_session, claim_id) is S.UPLOADED


async def test_database_refuses_transition_that_skips_the_service(
    db_session: AsyncSession,
) -> None:
    claim_id = await new_claim(db_session, S.UPLOADED)

    with pytest.raises(IntegrityError, match="cannot change from uploaded to approved"):
        await db_session.execute(
            text("UPDATE claims SET status = 'approved' WHERE id = :id"), {"id": claim_id}
        )


async def test_transitions_table_matches_contracts(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        select(ClaimStatusTransition.from_status, ClaimStatusTransition.to_status)
    )

    assert {tuple(row) for row in rows} == set(ALLOWED)


@pytest.mark.parametrize("run", [1, 2])
async def test_tests_do_not_see_each_others_data(db_session: AsyncSession, run: int) -> None:
    # Runs twice: if the first run's claim leaked, the second would count two.
    await new_claim(db_session)

    count = await db_session.scalar(select(func.count()).select_from(Claim))

    assert count == 1
