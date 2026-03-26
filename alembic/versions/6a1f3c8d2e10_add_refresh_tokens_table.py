"""Add refresh_tokens table for refresh JWT rotation.

Revision ID: 6a1f3c8d2e10
Revises: 4c7d2a1e9f00
Create Date: 2026-03-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6a1f3c8d2e10"
down_revision: Union[str, None] = "4c7d2a1e9f00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_revoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("device_info", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_refresh_tokens_user_id_is_revoked",
        "refresh_tokens",
        ["user_id", "is_revoked"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id_is_revoked", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
