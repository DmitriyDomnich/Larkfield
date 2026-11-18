"""GET /claims/{id}/extraction against a real PostgreSQL."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_token_verifier
from app.claims.models import Document
from app.claims.storage import get_storage
from app.core.config import Settings
from app.core.db import get_session
from app.extraction.models import Extraction
from app.main import create_app
from tests.claims.fakes import FakeStorage, auth, claim_body
from tests.extraction.fakes import label
from tests.review.db import extracted_claim
from tests.tokens import make_verifier

pytestmark = pytest.mark.integration

EMPLOYEE = "employee-1"
SUM_MISMATCH = {
    "code": "sum_mismatch",
    "message": "Items, tax and tip add up to 10, the total is 12",
}


@pytest.fixture
async def api(db_session: AsyncSession, settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_token_verifier] = lambda: make_verifier(settings)
    app.dependency_overrides[get_storage] = FakeStorage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def as_(settings: Settings) -> Any:
    def headers(sub: str = EMPLOYEE, role: str = "employee") -> dict[str, str]:
        return auth(settings, sub=sub, role=role)

    return headers


@pytest.fixture
async def claim_id(db_session: AsyncSession) -> uuid.UUID:
    claim_id = await extracted_claim(db_session, "D01", employee_sub=EMPLOYEE)
    await db_session.execute(
        update(Extraction)
        .where(Extraction.document_id == Document.id, Document.claim_id == claim_id)
        .values(warnings=[SUM_MISMATCH])
    )
    await db_session.commit()
    return claim_id


@pytest.mark.parametrize(
    "caller", [{}, {"sub": "reviewer-1", "role": "reviewer"}], ids=["owner", "reviewer"]
)
async def test_owner_and_reviewer_get_the_extraction(
    api: AsyncClient, as_: Any, claim_id: uuid.UUID, caller: dict[str, str]
) -> None:
    response = await api.get(f"/claims/{claim_id}/extraction", headers=as_(**caller))

    assert response.status_code == 200, response.text
    body = response.json()
    expected = label("D01")
    assert body["vendor_name"] == expected["vendor_name"]
    assert body["total"] == expected["total"]  # money stays a string
    assert [item["description"] for item in body["line_items"]] == [
        item["description"] for item in expected["line_items"]
    ]
    assert body["warnings"] == [SUM_MISMATCH]
    assert body["ai_model"] == "eu.anthropic.test-model"
    assert body["created_at"]


async def test_other_employees_claim_and_a_random_id_get_the_same_404(
    api: AsyncClient, as_: Any, claim_id: uuid.UUID
) -> None:
    others = await api.get(f"/claims/{claim_id}/extraction", headers=as_(sub="employee-2"))
    missing = await api.get(f"/claims/{uuid.uuid4()}/extraction", headers=as_())

    assert others.status_code == missing.status_code == 404
    assert others.json() == missing.json() == {"detail": "Claim not found"}


async def test_claim_not_yet_extracted_has_no_extraction(api: AsyncClient, as_: Any) -> None:
    created = await api.post("/claims", json=claim_body(), headers=as_())
    claim_id = created.json()["claim"]["id"]

    response = await api.get(f"/claims/{claim_id}/extraction", headers=as_())

    assert response.status_code == 404
    assert response.json() == {"detail": "The claim has no extraction yet"}
