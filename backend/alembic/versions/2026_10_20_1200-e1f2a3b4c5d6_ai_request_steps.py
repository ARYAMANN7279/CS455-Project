"""Store tool steps on AI request audit records.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_assistant_requests", sa.Column("steps", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_assistant_requests", "steps")
