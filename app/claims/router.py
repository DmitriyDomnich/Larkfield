import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_roles
from app.auth.roles import Role
from app.claims import service
from app.claims.schemas import ClaimCreate, ClaimCreated, ClaimPage, ClaimRead, FileLink
from app.claims.service import (
    ClaimNotFoundError,
    FileNotAvailableError,
    InvalidTransitionError,
)
from app.claims.status import ClaimStatus
from app.claims.storage import ObjectStorage, get_storage
from app.core.config import Settings, get_settings
from app.core.db import get_session


class ErrorDetail(BaseModel):
    detail: str


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        401: "Missing or invalid access token",
        403: "The caller's role may not use this endpoint",
        404: "No such claim, or the caller may not see it (the two are indistinguishable)",
        409: "The claim's status does not allow this",
        422: "Invalid request",
    }
    return {code: {"model": ErrorDetail, "description": descriptions[code]} for code in codes}


ClaimsUser = Annotated[CurrentUser, Depends(require_roles(Role.EMPLOYEE, Role.REVIEWER))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

router = APIRouter(prefix="/claims", tags=["claims"], responses=_errors(401, 403))


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ClaimCreated,
    summary="Submit a claim",
    description=(
        "Creates the claim in `pending_upload` and returns a presigned S3 form. Upload the file "
        "to `upload.url` as multipart/form-data with every entry of `upload.fields` before the "
        "file. The upload starts processing by itself: poll `GET /claims/{id}` to follow the "
        "status (`uploaded`, `extracting`, then `extracted` or `failed` with a reason)."
    ),
    responses=_errors(422),
)
async def create_claim(
    body: ClaimCreate,
    user: ClaimsUser,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> ClaimCreated:
    claim, upload = await service.create_claim(session, storage, settings, user, body)
    return ClaimCreated(claim=ClaimRead.model_validate(claim), upload=upload)


@router.get(
    "",
    response_model=ClaimPage,
    summary="List claims",
    description=("Employees see their own claims, reviewers all claims; newest first"),
    responses=_errors(422),
)
async def list_claims(
    user: ClaimsUser,
    session: SessionDep,
    status_filter: Annotated[list[ClaimStatus] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClaimPage:
    claims, total = await service.list_claims(session, user, status_filter or [], limit, offset)
    return ClaimPage(
        items=[ClaimRead.model_validate(claim) for claim in claims],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{claim_id}",
    response_model=ClaimRead,
    summary="Get a claim",
    responses=_errors(404),
)
async def get_claim(claim_id: uuid.UUID, user: ClaimsUser, session: SessionDep) -> ClaimRead:
    try:
        claim = await service.get_claim(session, user, claim_id)
    except ClaimNotFoundError:
        raise not_found() from None
    return ClaimRead.model_validate(claim)


@router.get(
    "/{claim_id}/file",
    response_model=FileLink,
    summary="Get a link to view the claim's file",
    description="A presigned S3 link that expires within minutes. 404 until the file is verified.",
    responses=_errors(404),
)
async def get_file_link(
    claim_id: uuid.UUID,
    user: ClaimsUser,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> FileLink:
    try:
        return await service.file_link(session, storage, settings, user, claim_id)
    except ClaimNotFoundError:
        raise not_found() from None
    except FileNotAvailableError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The claim has no file yet") from None


async def transition_refused(request: Request, exc: Exception) -> JSONResponse:
    """Handle claim status transition errors"""
    if isinstance(exc, InvalidTransitionError):
        detail = f"The claim cannot move from {exc.current} to {exc.target}"
    else:
        detail = "The claim's status changed in the meantime; reload it and try again"
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": detail})
