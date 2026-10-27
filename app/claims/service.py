import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.models import Claim
from app.claims.status import ClaimStatus, can_transition


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
    Move a claim to `target` if's allowed from its current status.
    The database trigger enforces the same rule for anything that skips this function.
    """
    if (target is ClaimStatus.FAILED) != (failure_reason is not None):
        raise ValueError("failure_reason is required for the failed status")

    current = await session.scalar(select(Claim.status).where(Claim.id == claim_id))
    if current is None:
        raise ClaimNotFoundError(claim_id)
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)

    try:
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
