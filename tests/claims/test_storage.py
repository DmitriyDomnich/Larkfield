"""S3ObjectStorage against botocore with fake credentials: signing is local, and calls that would
reach S3 go to a Stubber."""

import base64
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.claims.files import MAX_FILE_BYTES
from app.claims.storage import S3ObjectStorage
from app.core.config import Settings


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")


@pytest.fixture
def stubbed(settings: Settings) -> Iterator[tuple[S3ObjectStorage, Stubber]]:
    client = boto3.client("s3", region_name=settings.aws_region)
    with Stubber(client) as stubber:
        yield S3ObjectStorage(settings, client=client), stubber
        stubber.assert_no_pending_responses()


async def test_upload_policy_binds_key_type_and_size(settings: Settings) -> None:
    storage = S3ObjectStorage(settings)

    post = await storage.presigned_post("claims/c/d", "application/pdf", MAX_FILE_BYTES, 600)

    assert post.url == (
        f"https://{settings.documents_bucket}.s3.{settings.aws_region}.amazonaws.com/"
    )
    assert post.fields["key"] == "claims/c/d"
    policy = json.loads(base64.b64decode(post.fields["policy"]))
    conditions = policy["conditions"]
    assert {"bucket": settings.documents_bucket} in conditions
    assert {"key": "claims/c/d"} in conditions
    assert {"Content-Type": "application/pdf"} in conditions
    assert ["content-length-range", 1, 10 * 1024 * 1024] in conditions
    expires = datetime.fromisoformat(policy["expiration"])
    assert abs(expires - (datetime.now(UTC) + timedelta(seconds=600))) < timedelta(seconds=5)


async def test_view_link_expires_and_forces_the_verified_type(settings: Settings) -> None:
    storage = S3ObjectStorage(settings)

    url = await storage.presigned_get("claims/c/d", "image/png", 'inline; filename="a.png"', 300)

    query = parse_qs(urlsplit(url).query)
    assert query["X-Amz-Expires"] == ["300"]
    assert query["response-content-type"] == ["image/png"]
    assert query["response-content-disposition"] == ['inline; filename="a.png"']


async def test_size_of_existing_and_missing_object(
    stubbed: tuple[S3ObjectStorage, Stubber], settings: Settings
) -> None:
    storage, stubber = stubbed
    params = {"Bucket": settings.documents_bucket, "Key": "claims/c/d"}
    stubber.add_response("head_object", {"ContentLength": 42}, params)
    stubber.add_client_error("head_object", "404", http_status_code=404, expected_params=params)

    assert await storage.size("claims/c/d") == 42
    assert await storage.size("claims/c/d") is None


async def test_size_reraises_other_errors(stubbed: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("head_object", "403", http_status_code=403)

    with pytest.raises(Exception, match="403"):
        await storage.size("claims/c/d")


async def test_read_first_bytes_requests_only_those_bytes(
    stubbed: tuple[S3ObjectStorage, Stubber], settings: Settings
) -> None:
    storage, stubber = stubbed
    body = StreamingBody(io.BytesIO(b"%PDF-1.7"), 8)
    stubber.add_response(
        "get_object",
        {"Body": body},
        {"Bucket": settings.documents_bucket, "Key": "claims/c/d", "Range": "bytes=0-7"},
    )

    assert await storage.read_first_bytes("claims/c/d", 8) == b"%PDF-1.7"


async def test_read_whole_object(
    stubbed: tuple[S3ObjectStorage, Stubber], settings: Settings
) -> None:
    storage, stubber = stubbed
    body = StreamingBody(io.BytesIO(b"%PDF-1.7 whole"), 14)
    stubber.add_response(
        "get_object", {"Body": body}, {"Bucket": settings.documents_bucket, "Key": "claims/c/d"}
    )

    assert await storage.read("claims/c/d") == b"%PDF-1.7 whole"


async def test_delete(stubbed: tuple[S3ObjectStorage, Stubber], settings: Settings) -> None:
    storage, stubber = stubbed
    stubber.add_response(
        "delete_object", {}, {"Bucket": settings.documents_bucket, "Key": "claims/c/d"}
    )

    await storage.delete("claims/c/d")


async def test_view_link_of_a_version(settings: Settings) -> None:
    storage = S3ObjectStorage(settings)

    url = await storage.presigned_get("claims/c/d", "image/png", "inline", 300, version_id="v1")

    assert parse_qs(urlsplit(url).query)["versionId"] == ["v1"]


async def test_calls_on_a_version_name_it(
    stubbed: tuple[S3ObjectStorage, Stubber], settings: Settings
) -> None:
    storage, stubber = stubbed
    version = {"Bucket": settings.documents_bucket, "Key": "claims/c/d", "VersionId": "v1"}
    stubber.add_response("head_object", {"ContentLength": 8}, version)
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(b"%PDF-"), 5)},
        version | {"Range": "bytes=0-4"},
    )
    stubber.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"%PDF-1.7"), 8)}, version)
    stubber.add_response("delete_object", {}, version)

    assert await storage.size("claims/c/d", "v1") == 8
    assert await storage.read_first_bytes("claims/c/d", 5, "v1") == b"%PDF-"
    assert await storage.read("claims/c/d", "v1") == b"%PDF-1.7"
    await storage.delete("claims/c/d", "v1")
