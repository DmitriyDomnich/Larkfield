from enum import StrEnum


class ClaimStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_INFO = "needs_info"
    FAILED = "failed"


INITIAL_STATUS = ClaimStatus.PENDING_UPLOAD

ALLOWED_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.PENDING_UPLOAD: frozenset({ClaimStatus.UPLOADED}),
    ClaimStatus.UPLOADED: frozenset({ClaimStatus.EXTRACTING}),
    ClaimStatus.EXTRACTING: frozenset({ClaimStatus.EXTRACTED, ClaimStatus.FAILED}),
    ClaimStatus.EXTRACTED: frozenset({ClaimStatus.IN_REVIEW, ClaimStatus.FAILED}),
    ClaimStatus.IN_REVIEW: frozenset(
        {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.NEEDS_INFO}
    ),
    ClaimStatus.NEEDS_INFO: frozenset({ClaimStatus.EXTRACTED}),
    ClaimStatus.APPROVED: frozenset(),
    ClaimStatus.REJECTED: frozenset(),
    ClaimStatus.FAILED: frozenset(),
}

FINAL_STATUSES = frozenset(s for s, targets in ALLOWED_TRANSITIONS.items() if not targets)


def can_transition(current: ClaimStatus, target: ClaimStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
