import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.models import Claim
from app.claims.status import ClaimStatus


class ClaimNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    def __init__(self, current: ClaimStatus, target: ClaimStatus) -> None:
        super().__init__(f"claim status cannot change from {current} to {target}")
        self.current = current
        self.target = target


class ConcurrentTransitionError(Exception):
    """The status changed between reading it and updating it."""


async def transition(
    session: AsyncSession,
    claim_id: uuid.UUID,
    target: ClaimStatus,
    *,
    failure_reason: str | None = None,
) -> None:
    """
    Move a claim to `target`. Whether the move is allowed is decided by the database (the
    `claim_status_transitions` table and the trigger on `claims`).
    """
    if (target is ClaimStatus.FAILED) != (failure_reason is not None):
        raise ValueError("failure_reason is required for the failed status")

    current = await session.scalar(select(Claim.status).where(Claim.id == claim_id))
    if current is None:
        raise ClaimNotFoundError(claim_id)

    try:
        # savepoint: a refused move rolls back only this update, not the caller's transaction.
        async with session.begin_nested():
            updated = await session.scalar(
                update(Claim)
                .where(Claim.id == claim_id, Claim.status == current)
                .values(status=target, failure_reason=failure_reason)
                .returning(Claim.id)
            )
    except IntegrityError as exc:
        raise InvalidTransitionError(current, target) from exc
    if updated is None:
        raise ConcurrentTransitionError(claim_id)
