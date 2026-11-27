import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class ClaimListQuery(BaseModel):
    status: list[ClaimStatus] = []
    submitted_after: AwareDatetime | None = Field(default=None, description="Inclusive")
    submitted_before: AwareDatetime | None = Field(default=None, description="Exclusive")
    employee_sub: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    offset: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _range_is_not_reversed(self) -> Self:
        after, before = self.submitted_after, self.submitted_before
        if after is not None and before is not None and after > before:
            raise ValueError("submitted_after must not be later than submitted_before")
        return self


class ClaimPage(BaseModel):
    items: list[ClaimRead]
    total: int
    limit: int
    offset: int


class FileLink(BaseModel):
    url: str
    expires_at: datetime
