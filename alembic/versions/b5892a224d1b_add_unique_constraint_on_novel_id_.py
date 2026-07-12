"""add unique constraint on novel_id policy_id

Revision ID: b5892a224d1b
Revises: ca52ef6ed9cd
Create Date: 2026-07-12 01:46:02.949066

"""

from typing import Sequence, Union

from sqlalchemy import inspect

from alembic import op

revision: str = "b5892a224d1b"
down_revision: Union[str, Sequence[str], None] = "ca52ef6ed9cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    constraints = [u["name"] for u in inspector.get_unique_constraints(table_name)]
    return constraint_name in constraints


def upgrade() -> None:
    if not _constraint_exists("policies", "uq_novel_policy"):
        with op.batch_alter_table("policies", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_novel_policy", ["novel_id", "policy_id"])


def downgrade() -> None:
    if _constraint_exists("policies", "uq_novel_policy"):
        with op.batch_alter_table("policies", schema=None) as batch_op:
            batch_op.drop_constraint("uq_novel_policy", type_="unique")
