"""seed claim statuses and transitions

Revision ID: 63ff96d8e7f7
Revises: 6ff4d350e89c
Create Date: 2026-10-26 17:41:49.385649
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "63ff96d8e7f7"
down_revision: str | Sequence[str] | None = "6ff4d350e89c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Status data migration
STATUSES = (
    "pending_upload",
    "uploaded",
    "extracting",
    "extracted",
    "in_review",
    "approved",
    "rejected",
    "needs_info",
    "failed",
)
TRANSITIONS = (
    ("pending_upload", "uploaded"),
    ("uploaded", "extracting"),
    ("extracting", "extracted"),
    ("extracting", "failed"),
    ("extracted", "in_review"),
    ("extracted", "failed"),
    ("in_review", "approved"),
    ("in_review", "rejected"),
    ("in_review", "needs_info"),
    ("needs_info", "extracted"),
)

claim_statuses = sa.table("claim_statuses", sa.column("code", sa.String))
claim_status_transitions = sa.table(
    "claim_status_transitions",
    sa.column("from_status", sa.String),
    sa.column("to_status", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(claim_statuses, [{"code": code} for code in STATUSES])
    op.bulk_insert(
        claim_status_transitions,
        [{"from_status": a, "to_status": b} for a, b in TRANSITIONS],
    )


def downgrade() -> None:
    op.execute(claim_status_transitions.delete())
    op.execute(claim_statuses.delete())
