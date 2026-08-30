"""baseline: reflect current live schema

Revision ID: 0001
Revises:
Create Date: 2026-08-30

This migration intentionally does nothing on upgrade — it exists as the
starting point for a database that already has all tables/columns created
by create_all() at some point. Stamp existing databases with:

    alembic stamp 0001

New databases should run `alembic upgrade head` after tables are created,
or better: drop the create_all() call and let Alembic own table creation
going forward via `alembic upgrade head` alone.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
