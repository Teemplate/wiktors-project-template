"""initial: items table

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-23

The template's one example table. Replace it with the app's real schema — but
keep a first revision, so that `alembic upgrade head` on an empty database is
the only way the schema is ever created. Creating tables from
`Base.metadata.create_all()` instead leaves migrations and reality permanently
out of step.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    # Dropping the table this revision created is not data loss in the sense the
    # CI guard cares about — the guard only inspects upgrade().
    op.drop_table("items")
