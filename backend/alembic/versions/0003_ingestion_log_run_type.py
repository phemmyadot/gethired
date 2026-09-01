"""add run_type to ingestion_logs

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_logs",
        sa.Column("run_type", sa.String(20), nullable=True, server_default="pipeline"),
    )


def downgrade() -> None:
    op.drop_column("ingestion_logs", "run_type")
