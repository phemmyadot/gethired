"""track the last successful pool time for each source

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("source_pool_states"):
        op.create_table(
            "source_pool_states",
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("last_pooled_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("source"),
        )


def downgrade() -> None:
    op.drop_table("source_pool_states")
