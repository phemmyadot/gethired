"""add discovered_ats_companies table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovered_ats_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("board_token", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("company_name", "source", name="uq_discovered_company_source"),
    )


def downgrade() -> None:
    op.drop_table("discovered_ats_companies")
