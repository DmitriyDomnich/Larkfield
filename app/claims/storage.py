"""The documents bucket"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import Request

from app.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass(frozen=True)
class PresignedPost:
    """A form the browser POSTs to `url`: every field from `fields`, then the file."""

    url: str
    fields: dict[str, str]


class ObjectStorage(Protocol):
    async def presigned_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost: ...

    async def presigned_get(
        self, key: str, content_type: str, content_disposition: str, expires_in: int
    ) -> str: ...

    async def size(self, key: str) -> int | None:
        """Size in bytes, or None if there is no such object."""
        ...

    async def read_first_bytes(self, key: str, length: int) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class S3ObjectStorage:
    def __init__(self, settings: Settings, client: "S3Client | None" = None) -> None:
        self._bucket = settings.documents_bucket
        self._client = client or boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=f"https://s3.{settings.aws_region}.amazonaws.com",
            config=Config(s3={"addressing_style": "virtual"}),
        )

    async def presigned_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        post = await asyncio.to_thread(
            self._client.generate_presigned_post,
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=expires_in,
        )
        return PresignedPost(url=post["url"], fields=post["fields"])

    async def presigned_get(
        self, key: str, content_type: str, content_disposition: str, expires_in: int
    ) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": content_disposition,
            },
            ExpiresIn=expires_in,
        )

    async def size(self, key: str) -> int | None:
        try:
            head = await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return head["ContentLength"]

    async def read_first_bytes(self, key: str, length: int) -> bytes:
        return await asyncio.to_thread(self._read_first_bytes, key, length)

    def _read_first_bytes(self, key: str, length: int) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key, Range=f"bytes=0-{length - 1}")
        return obj["Body"].read()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)


def get_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage = request.app.state.storage
    return storage
