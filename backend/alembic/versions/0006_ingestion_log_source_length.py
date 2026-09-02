"""widen ingestion_logs.source to fit all-source comma list

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ingestion_logs", "source",
        existing_type=sa.String(50),
        type_=sa.String(255),
    )


def downgrade() -> None:
    op.alter_column(
        "ingestion_logs", "source",
        existing_type=sa.String(255),
        type_=sa.String(50),
    )
