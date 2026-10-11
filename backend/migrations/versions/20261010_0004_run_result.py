"""Store validated per-round accuracy on runs.

Revision ID: 20261010_0004
Revises: 20261008_0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261010_0004"
down_revision = "20261008_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("result", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "result")
