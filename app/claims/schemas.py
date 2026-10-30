import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.claims.files import MAX_FILE_BYTES, ContentType
from app.claims.status import ClaimStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Attendee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    company: Name


class FileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    content_type: ContentType
    size_bytes: Annotated[int, Field(ge=1, le=MAX_FILE_BYTES)]


class ClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Annotated[str, StringConstraints(min_length=10, max_length=500)]
    attendees: Annotated[list[Attendee], Field(max_length=50)] = []
    preapproval_ref: Annotated[str, StringConstraints(pattern=r"^PA-[0-9]{4}-[0-9]{3}$")] | None = (
        None
    )
    file: FileSpec


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    original_filename: str
    content_type: str
    size_bytes: int | None


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_sub: str
    status: ClaimStatus
    purpose: str
    attendees: list[Attendee]
    preapproval_ref: str | None
    failure_reason: str | None
    submitted_at: datetime
    updated_at: datetime
    document: DocumentRead | None


class UploadForm(BaseModel):
    """POST to `url` as multipart/form-data: every entry of `fields`, then `file` last."""

    url: str
    fields: dict[str, str]
    expires_at: datetime


class ClaimCreated(BaseModel):
    claim: ClaimRead
    upload: UploadForm


class ClaimPage(BaseModel):
    items: list[ClaimRead]
    total: int
    limit: int
    offset: int


class FileLink(BaseModel):
    url: str
    expires_at: datetime
