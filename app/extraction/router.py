import uuid

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import ClaimsUser
from app.claims.router import ErrorDetail, claim_not_found
from app.claims.service import ClaimNotFoundError
from app.core.db import SessionDep
from app.extraction import service
from app.extraction.schemas import ExtractionRead
from app.extraction.service import ExtractionNotFoundError

ERROR_DESCRIPTIONS = {
    401: "Missing or invalid access token",
    403: "The caller's role may not use this endpoint",
    404: "No such claim, the caller may not see it, or it has no extraction yet",
}

router = APIRouter(
    prefix="/claims",
    tags=["extraction"],
    responses={
        code: {"model": ErrorDetail, "description": description}
        for code, description in ERROR_DESCRIPTIONS.items()
    },
)


@router.get(
    "/{claim_id}/extraction",
    response_model=ExtractionRead,
    summary="Get the fields extracted from a claim's document",
    description=(
        "The extracted fields, line items and the sanity checks they failed. Employees see their "
        "own claims, reviewers all claims. 404 until the claim reaches `extracted`."
    ),
)
async def get_extraction(
    claim_id: uuid.UUID, user: ClaimsUser, session: SessionDep
) -> ExtractionRead:
    try:
        extraction = await service.get_extraction(session, user, claim_id)
    except ClaimNotFoundError:
        raise claim_not_found() from None
    except ExtractionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The claim has no extraction yet") from None
    return ExtractionRead.model_validate(extraction, from_attributes=True)
