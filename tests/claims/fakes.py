"""An in-memory documents bucket and auth headers for the claims tests."""

from app.claims.storage import PresignedPost
from app.core.config import Settings
from tests.tokens import make_token

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00"


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def presigned_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        return PresignedPost(
            url="https://bucket.example/", fields={"key": key, "Content-Type": content_type}
        )

    async def presigned_get(
        self, key: str, content_type: str, content_disposition: str, expires_in: int
    ) -> str:
        return f"https://bucket.example/{key}?X-Amz-Expires={expires_in}"

    async def size(self, key: str) -> int | None:
        data = self.objects.get(key)
        return None if data is None else len(data)

    async def read_first_bytes(self, key: str, length: int) -> bytes:
        return self.objects[key][:length]

    async def delete(self, key: str) -> None:
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
