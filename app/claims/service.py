import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser
from app.auth.roles import Role
from app.claims.files import (
    BYTES_TO_CHECK,
    LABELS,
    MAX_FILE_BYTES,
    content_disposition,
    content_matches_type,
)
from app.claims.models import Claim, Document
from app.claims.schemas import ClaimCreate, FileLink, UploadForm
from app.claims.status import ClaimStatus
from app.claims.storage import ObjectStorage
from app.core.config import Settings


class ClaimNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    def __init__(self, current: ClaimStatus, target: ClaimStatus) -> None:
        super().__init__(f"claim status cannot change from {current} to {target}")
        self.current = current
        self.target = target


class ConcurrentTransitionError(Exception):
    """The status changed between reading it and updating it."""


class FileNotUploadedError(Exception):
    """The claim's file is not in S3 (yet)."""


class RejectedFileError(Exception):
    """The uploaded file is not what was declared; the claim is now failed with `reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FileNotAvailableError(Exception):
    """The claim has no verified file to show."""


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


def _visible_to(user: CurrentUser) -> list[ColumnElement[bool]]:
    """Reviewers see every claim; anyone else only their own"""
    return [] if user.role is Role.REVIEWER else [Claim.employee_sub == user.sub]


def _with_document() -> Select[Claim]:
    return (
        select(Claim)
        .options(selectinload(Claim.document))
        .execution_options(populate_existing=True)
    )


async def get_claim(session: AsyncSession, user: CurrentUser, claim_id: uuid.UUID) -> Claim:
    claim = await session.scalar(_with_document().where(Claim.id == claim_id, *_visible_to(user)))
    if claim is None:
        raise ClaimNotFoundError(claim_id)
    return claim


async def list_claims(
    session: AsyncSession,
    user: CurrentUser,
    statuses: Sequence[ClaimStatus],
    limit: int,
    offset: int,
) -> tuple[list[Claim], int]:
    filters = _visible_to(user)
    if statuses:
        filters.append(Claim.status.in_(statuses))

    total = await session.scalar(select(func.count()).select_from(Claim).where(*filters)) or 0
    claims = await session.scalars(
        _with_document()
        .where(*filters)
        .order_by(Claim.submitted_at.desc(), Claim.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(claims), total


async def create_claim(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    user: CurrentUser,
    data: ClaimCreate,
) -> tuple[Claim, UploadForm]:
    """Create a claim in pending_upload and a form the browser uploads its file to S3 with."""
    claim = Claim(
        employee_sub=user.sub,
        purpose=data.purpose,
        attendees=[attendee.model_dump() for attendee in data.attendees],
        preapproval_ref=data.preapproval_ref,
    )
    session.add(claim)
    await session.flush()

    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        claim_id=claim.id,
        s3_key=f"claims/{claim.id}/{document_id}",
        original_filename=data.file.filename,
        content_type=data.file.content_type,
    )
    session.add(document)
    await session.flush()

    expires_at = datetime.now(UTC) + timedelta(seconds=settings.upload_url_ttl_seconds)
    post = await storage.presigned_post(
        f"claims/{claim.id}/{document_id}",
        data.file.content_type,
        MAX_FILE_BYTES,
        settings.upload_url_ttl_seconds,
    )
    await session.commit()
    upload = UploadForm(url=post.url, fields=post.fields, expires_at=expires_at)
    return await get_claim(session, user, claim.id), upload


async def confirm_upload(
    session: AsyncSession, storage: ObjectStorage, user: CurrentUser, claim_id: uuid.UUID
) -> Claim:
    claim = await session.scalar(
        _with_document()
        .where(Claim.id == claim_id, Claim.employee_sub == user.sub)
        .with_for_update(of=Claim)
    )
    if claim is None or claim.document is None:
        raise ClaimNotFoundError(claim_id)
    if claim.status is not ClaimStatus.PENDING_UPLOAD:
        raise InvalidTransitionError(claim.status, ClaimStatus.UPLOADED)

    document = claim.document
    size = await storage.size(document.s3_key)
    if size is None:
        raise FileNotUploadedError(claim_id)

    reason = None
    if size > MAX_FILE_BYTES:
        reason = "The file is larger than 10 MB"
    elif not content_matches_type(
        await storage.read_first_bytes(document.s3_key, BYTES_TO_CHECK), document.content_type
    ):
        reason = f"The file is not a valid {LABELS[document.content_type]}"

    if reason is not None:
        await storage.delete(document.s3_key)
        await transition(session, claim.id, ClaimStatus.FAILED, failure_reason=reason)
        await session.commit()
        raise RejectedFileError(reason)

    document.size_bytes = size
    await transition(session, claim.id, ClaimStatus.UPLOADED)
    await session.commit()
    return await get_claim(session, user, claim.id)


async def file_link(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    user: CurrentUser,
    claim_id: uuid.UUID,
) -> FileLink:
    claim = await get_claim(session, user, claim_id)
    document = claim.document
    if document is None or document.size_bytes is None:
        raise FileNotAvailableError(claim_id)

    expires_at = datetime.now(UTC) + timedelta(seconds=settings.file_url_ttl_seconds)
    url = await storage.presigned_get(
        document.s3_key,
        document.content_type,
        content_disposition(document.original_filename),
        settings.file_url_ttl_seconds,
    )
    return FileLink(url=url, expires_at=expires_at)
