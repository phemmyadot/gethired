"""add key_skills to jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("key_skills", postgresql.ARRAY(sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "key_skills")
