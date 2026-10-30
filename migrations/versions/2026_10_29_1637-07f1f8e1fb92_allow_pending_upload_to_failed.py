"""allow pending_upload to failed

Revision ID: 07f1f8e1fb92
Revises: 63ff96d8e7f7
Create Date: 2026-10-29 16:37:30.699829
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "07f1f8e1fb92"
down_revision: str | Sequence[str] | None = "63ff96d8e7f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


claim_status_transitions = sa.table(
    "claim_status_transitions",
    sa.column("from_status", sa.String),
    sa.column("to_status", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(
        claim_status_transitions, [{"from_status": "pending_upload", "to_status": "failed"}]
    )


def downgrade() -> None:
    op.execute(
        claim_status_transitions.delete().where(
            claim_status_transitions.c.from_status == "pending_upload",
            claim_status_transitions.c.to_status == "failed",
        )
    )
