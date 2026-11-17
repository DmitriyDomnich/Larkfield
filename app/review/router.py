import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, require_roles
from app.auth.roles import Role
from app.claims.router import ErrorDetail, claim_not_found
from app.claims.service import ClaimNotFoundError
from app.core.db import get_session
from app.notifications.queue import NotificationService, get_notification_service, send_notification
from app.review import decisions
from app.review.decisions import CommentRequiredError, OwnClaimError
from app.review.queue import ReviewRequests, get_review_requests, send_review_request
from app.review.schemas import (
    AnswerCreate,
    AnswerRead,
    ClaimReview,
    DecisionCreate,
    ReviewerDecisionRead,
)

ERROR_DESCRIPTIONS = {
    401: "Missing or invalid access token",
    403: "The caller's role may not use this endpoint, or a reviewer decides their own claim",
    404: "No such claim, or the caller may not see it (the two are indistinguishable)",
    409: "The claim's status does not allow this",
    422: "Invalid request, or a comment is missing where one is required",
}


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorDetail, "description": ERROR_DESCRIPTIONS[code]} for code in codes}


ReviewerUser = Annotated[CurrentUser, Depends(require_roles(Role.REVIEWER))]
ClaimsUser = Annotated[CurrentUser, Depends(require_roles(Role.EMPLOYEE, Role.REVIEWER))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
ReviewRequestsDep = Annotated[ReviewRequests, Depends(get_review_requests)]

router = APIRouter(prefix="/claims", tags=["review"], responses=_errors(401, 403))


@router.post(
    "/{claim_id}/decision",
    status_code=status.HTTP_201_CREATED,
    response_model=ReviewerDecisionRead,
    summary="Decide a claim in review",
    description=(
        "Reviewers only, never on their own claim. Decides the claim's latest proposal: the "
        "claim moves to `approved`, `rejected` or `needs_info` and the employee is emailed. "
        "`comment` is required when the decision differs from the proposal or is `needs_info`."
    ),
    responses=_errors(404, 409, 422),
)
async def decide_claim(
    claim_id: uuid.UUID,
    body: DecisionCreate,
    reviewer: ReviewerUser,
    session: SessionDep,
    notification_service: NotificationServiceDep,
    background_tasks: BackgroundTasks,
) -> ReviewerDecisionRead:
    try:
        decision, notification = await decisions.decide_claim(session, reviewer, claim_id, body)
    except ClaimNotFoundError:
        raise claim_not_found() from None
    except OwnClaimError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A reviewer cannot decide their own claim"
        ) from None
    except CommentRequiredError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A comment is required when the decision differs from the proposal or is needs_info",
        ) from None
    background_tasks.add_task(send_notification, notification_service, notification)
    return ReviewerDecisionRead.model_validate(decision)


@router.post(
    "/{claim_id}/answer",
    status_code=status.HTTP_201_CREATED,
    response_model=AnswerRead,
    summary="Answer a needs_info request",
    description=(
        "The claim's owner answers the reviewer: `message`, plus any of `purpose`, `attendees` "
        "and `preapproval_ref` to change on the claim. The claim moves back to `extracted` and "
        "the agent reviews it again; follow it with `GET /claims/{id}`."
    ),
    responses=_errors(404, 409, 422),
)
async def answer_claim(
    claim_id: uuid.UUID,
    body: AnswerCreate,
    user: ClaimsUser,
    session: SessionDep,
    review_requests: ReviewRequestsDep,
    background_tasks: BackgroundTasks,
) -> AnswerRead:
    try:
        answer = await decisions.answer_claim(session, user, claim_id, body)
    except ClaimNotFoundError:
        raise claim_not_found() from None
    background_tasks.add_task(send_review_request, review_requests, claim_id)
    return AnswerRead.model_validate(answer)


@router.get(
    "/{claim_id}/review",
    response_model=ClaimReview,
    summary="Get a claim's review history",
    description=(
        "Every proposal with its decision and answer, newest first. Employees see their own "
        "claims, without the agent's proposals."
    ),
    responses=_errors(404),
)
async def get_claim_review(
    claim_id: uuid.UUID, user: ClaimsUser, session: SessionDep
) -> ClaimReview:
    try:
        return await decisions.get_claim_review(session, user, claim_id)
    except ClaimNotFoundError:
        raise claim_not_found() from None
