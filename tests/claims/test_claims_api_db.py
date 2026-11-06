"""Claims endpoints against a real PostgreSQL. S3 is the in-memory FakeStorage."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_token_verifier
from app.claims.models import Document
from app.claims.service import verify_upload
from app.claims.storage import get_storage
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from tests.claims.fakes import PDF, FakeStorage, auth, claim_body
from tests.tokens import make_verifier

pytestmark = pytest.mark.integration

REVIEWER = {"sub": "reviewer-1", "role": "reviewer"}


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
async def api(
    db_session: AsyncSession, settings: Settings, storage: FakeStorage
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_token_verifier] = lambda: make_verifier(settings)
    app.dependency_overrides[get_storage] = lambda: storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def as_(settings: Settings) -> Any:
    def headers(sub: str = "user-1", role: str = "employee") -> dict[str, str]:
        return auth(settings, sub=sub, role=role)

    return headers


async def submit(api: AsyncClient, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    response = await api.post("/claims", json={**claim_body(), **body}, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def upload(api: AsyncClient, storage: FakeStorage, headers: dict[str, str]) -> dict[str, Any]:
    """Submit a claim and put a PDF where the browser would; returns the created claim."""
    created = await submit(api, headers)
    storage.put(created["upload"]["fields"]["key"], PDF)
    claim: dict[str, Any] = created["claim"]
    return claim


async def verify(db_session: AsyncSession, storage: FakeStorage, claim_id: str) -> None:
    """What the extraction worker does first with the S3 event: the claim becomes `uploaded`."""
    document = await db_session.scalar(select(Document).where(Document.claim_id == claim_id))
    assert document is not None
    document.version_id = storage.current_version[document.s3_key]  # pinned from the S3 event
    assert await verify_upload(db_session, storage, document)
    await db_session.commit()


async def test_submit_creates_pending_claim_and_upload_form(
    api: AsyncClient, db_session: AsyncSession, as_: Any
) -> None:
    attendees = [{"name": "A. Novak", "company": "Meridian Health"}]

    created = await submit(api, as_(), attendees=attendees, preapproval_ref="PA-2026-114")

    claim, form = created["claim"], created["upload"]
    assert claim["status"] == "pending_upload"
    assert claim["employee_sub"] == "user-1"
    assert claim["attendees"] == attendees
    assert claim["preapproval_ref"] == "PA-2026-114"
    assert claim["document"] == {
        "original_filename": "receipt.pdf",
        "content_type": "application/pdf",
        "size_bytes": None,
    }
    document = await db_session.scalar(select(Document).where(Document.claim_id == claim["id"]))
    assert document is not None
    assert document.s3_key == form["fields"]["key"] == f"claims/{claim['id']}/{document.id}"
    expires_at = datetime.fromisoformat(form["expires_at"])
    assert expires_at - datetime.now(UTC) <= timedelta(minutes=10)


async def test_reviewer_can_submit_own_claim(api: AsyncClient, as_: Any) -> None:
    created = await submit(api, as_(**REVIEWER))

    assert created["claim"]["employee_sub"] == "reviewer-1"


async def test_employee_lists_only_own_claims(api: AsyncClient, as_: Any) -> None:
    mine = {(await submit(api, as_()))["claim"]["id"] for _ in range(2)}
    await submit(api, as_(sub="user-2"))

    page = (await api.get("/claims", headers=as_())).json()

    assert page["total"] == 2
    assert {item["id"] for item in page["items"]} == mine


async def test_other_employees_claim_is_indistinguishable_from_a_missing_one(
    api: AsyncClient, as_: Any
) -> None:
    claim = (await submit(api, as_()))["claim"]

    theirs = await api.get(f"/claims/{claim['id']}", headers=as_(sub="user-2"))
    missing = await api.get(f"/claims/{uuid.uuid4()}", headers=as_(sub="user-2"))

    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_reviewer_gets_any_claim(api: AsyncClient, as_: Any) -> None:
    claim = (await submit(api, as_()))["claim"]

    response = await api.get(f"/claims/{claim['id']}", headers=as_(**REVIEWER))

    assert response.status_code == 200
    assert response.json()["id"] == claim["id"]


async def test_reviewer_lists_all_claims_by_status_and_page(
    api: AsyncClient, db_session: AsyncSession, storage: FakeStorage, as_: Any
) -> None:
    uploaded = await upload(api, storage, as_())
    await verify(db_session, storage, uploaded["id"])
    await submit(api, as_(sub="user-2"))
    await submit(api, as_(sub="user-3"))
    reviewer = as_(**REVIEWER)

    by_status = (await api.get("/claims?status=uploaded", headers=reviewer)).json()
    several = (
        await api.get("/claims?status=uploaded&status=pending_upload", headers=reviewer)
    ).json()
    pages = [
        (await api.get(f"/claims?limit=2&offset={offset}", headers=reviewer)).json()
        for offset in (0, 2)
    ]

    assert [item["id"] for item in by_status["items"]] == [uploaded["id"]]
    assert several["total"] == 3
    assert [len(page["items"]) for page in pages] == [2, 1]
    assert all(page["total"] == 3 for page in pages)
    assert pages[1]["offset"] == 2
    ids = [item["id"] for page in pages for item in page["items"]]
    assert len(set(ids)) == 3


async def test_file_link_for_owner_and_reviewer_only(
    api: AsyncClient, db_session: AsyncSession, storage: FakeStorage, as_: Any, settings: Settings
) -> None:
    claim = await upload(api, storage, as_())
    path = f"/claims/{claim['id']}/file"
    before = await api.get(path, headers=as_())
    await verify(db_session, storage, claim["id"])

    owner = await api.get(path, headers=as_())
    reviewer = await api.get(path, headers=as_(**REVIEWER))
    other = await api.get(path, headers=as_(sub="user-2"))

    assert before.status_code == 404
    assert owner.status_code == reviewer.status_code == 200
    assert f"X-Amz-Expires={settings.file_url_ttl_seconds}" in owner.json()["url"]
    assert "versionId=v1" in owner.json()["url"]  # the version that was checked and extracted
    expires_at = datetime.fromisoformat(owner.json()["expires_at"])
    assert expires_at - datetime.now(UTC) <= timedelta(minutes=5)
    assert other.status_code == 404
    assert other.json() == {"detail": "Claim not found"}
