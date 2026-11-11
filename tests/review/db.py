import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.models import Claim, Document
from app.claims.service import transition
from app.claims.status import ClaimStatus as S
from app.extraction.models import Extraction, ExtractionLineItem
from tests.extraction.fakes import expense
from tests.review.fakes import review_case

TO_EXTRACTED = (S.UPLOADED, S.EXTRACTING, S.EXTRACTED)
AFTER_EXTRACTED = {
    S.EXTRACTED: (),
    S.IN_REVIEW: (S.IN_REVIEW,),
    S.APPROVED: (S.IN_REVIEW, S.APPROVED),
    S.REJECTED: (S.IN_REVIEW, S.REJECTED),
    S.NEEDS_INFO: (S.IN_REVIEW, S.NEEDS_INFO),
    S.FAILED: (S.FAILED,),
}


async def extracted_claim(
    session: AsyncSession,
    case_id: str,
    *,
    employee_sub: str = "employee-1",
    submitted_at: datetime | None = None,
    sha256: str | None = None,
    status: S = S.EXTRACTED,
    **expense_changes: Any,
) -> uuid.UUID:
    """A claim from a review case, extracted as its label says, then moved to `status`"""
    case = review_case(case_id)
    claim = Claim(
        employee_sub=employee_sub,
        purpose=case["claim"]["purpose"],
        attendees=case["claim"]["attendees"],
        preapproval_ref=case["claim"]["preapproval_ref"],
        submitted_at=submitted_at
        or datetime.combine(date.fromisoformat(case["submitted_at"]), time(9), UTC),
    )
    session.add(claim)
    await session.flush()
    document = Document(
        claim_id=claim.id,
        s3_key=f"claims/{claim.id}/{uuid.uuid4()}",
        original_filename=case["document"],
        content_type="application/pdf",
        sha256=sha256 or uuid.uuid4().hex * 2,
    )
    session.add(document)
    await session.flush()
    extracted = expense(case_id, **expense_changes)
    session.add(
        Extraction(
            document_id=document.id,
            **extracted.model_dump(exclude={"line_items"}),
            ai_model="eu.anthropic.test-model",
            line_items=[
                ExtractionLineItem(position=position, **item.model_dump())
                for position, item in enumerate(extracted.line_items)
            ],
        )
    )
    for step in TO_EXTRACTED + AFTER_EXTRACTED[status]:
        reason = "The document could not be read." if step is S.FAILED else None
        await transition(session, claim.id, step, failure_reason=reason)
    await session.commit()
    return claim.id
