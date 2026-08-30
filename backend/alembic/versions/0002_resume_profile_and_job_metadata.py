"""add resume profile fields, job work_mode/posted_at, ingestion_logs status

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resumes", sa.Column("search_keywords", sa.String(255), nullable=True))
    op.add_column("resumes", sa.Column("required_keywords", postgresql.ARRAY(sa.Text()), nullable=True))

    op.add_column("jobs", sa.Column("work_mode", sa.String(20), nullable=True))
    op.add_column("jobs", sa.Column("posted_at", sa.DateTime(), nullable=True))

    op.add_column("ingestion_logs", sa.Column("status", sa.String(20), nullable=True, server_default="running"))
    op.add_column("ingestion_logs", sa.Column("matches_found", sa.Float(), nullable=True, server_default="0"))


def downgrade() -> None:
    op.drop_column("ingestion_logs", "matches_found")
    op.drop_column("ingestion_logs", "status")

    op.drop_column("jobs", "posted_at")
    op.drop_column("jobs", "work_mode")

    op.drop_column("resumes", "required_keywords")
    op.drop_column("resumes", "search_keywords")
