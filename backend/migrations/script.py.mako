"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Before committing, check:
  - Does upgrade() drop a table or column? CI's destructive-migration guard
    fails the PR unless it carries the 'destructive-ok' label. Data loss is not
    reversible by a rebuild.
  - Is this the only new head? Two branches that each autogenerate a revision
    produce sibling heads, and `alembic upgrade head` then fails at deploy time.
    Re-point the newer revision's down_revision at the other.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
