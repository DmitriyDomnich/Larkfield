"""An in-memory documents bucket and auth headers for the claims tests."""

from app.claims.storage import PresignedPost
from app.core.config import Settings
from tests.tokens import make_token

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00"


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}  # current version of each key
        self.versions: dict[tuple[str, str], bytes] = {}
        self.current_version: dict[str, str] = {}
        self.deleted: list[str] = []

    def put(self, key: str, data: bytes) -> str:
        version_id = f"v{len(self.versions) + 1}"
        self.versions[(key, version_id)] = data
        self.objects[key] = data
        self.current_version[key] = version_id
        return version_id

    def _get(self, key: str, version_id: str | None) -> bytes | None:
        if version_id is None:
            return self.objects.get(key)
        return self.versions.get((key, version_id))

    async def presigned_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        return PresignedPost(
            url="https://bucket.example/", fields={"key": key, "Content-Type": content_type}
        )

    async def presigned_get(
        self,
        key: str,
        content_type: str,
        content_disposition: str,
        expires_in: int,
        version_id: str | None = None,
    ) -> str:
        version = f"&versionId={version_id}" if version_id else ""
        return f"https://bucket.example/{key}?X-Amz-Expires={expires_in}{version}"

    async def size(self, key: str, version_id: str | None = None) -> int | None:
        data = self._get(key, version_id)
        return None if data is None else len(data)

    async def read_first_bytes(self, key: str, length: int, version_id: str | None = None) -> bytes:
        data = self._get(key, version_id)
        assert data is not None
        return data[:length]

    async def read(self, key: str, version_id: str | None = None) -> bytes:
        data = self._get(key, version_id)
        assert data is not None
        return data

    async def delete(self, key: str, version_id: str | None = None) -> None:
        if version_id is not None:
            self.versions.pop((key, version_id), None)
        self.objects.pop(key, None)
        self.deleted.append(key)


def auth(settings: Settings, sub: str = "user-1", role: str = "employee") -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(settings, sub=sub, groups=[role])}"}


def claim_body(content_type: str = "application/pdf", size_bytes: int = 1000) -> dict[str, object]:
    return {
        "purpose": "Lunch during client workshop trip to Hamburg, project Orion",
        "attendees": [],
        "preapproval_ref": None,
        "file": {"filename": "receipt.pdf", "content_type": content_type, "size_bytes": size_bytes},
    }
