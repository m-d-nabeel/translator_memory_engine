"""add missing policy columns for sqlite ssot

Revision ID: ca52ef6ed9cd
Revises:
Create Date: 2026-07-12 00:49:48.038940

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "ca52ef6ed9cd"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table (idempotent migration)."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("policies", schema=None) as batch_op:
        if not _column_exists("policies", "scores"):
            batch_op.add_column(sa.Column("scores", sa.Text(), nullable=True))
        if not _column_exists("policies", "category"):
            batch_op.add_column(sa.Column("category", sa.String(), nullable=True))
        if not _column_exists("policies", "needs_review"):
            batch_op.add_column(
                sa.Column("needs_review", sa.String(), nullable=False, server_default="false")
            )
        if not _column_exists("policies", "llm_rejected"):
            batch_op.add_column(
                sa.Column("llm_rejected", sa.String(), nullable=False, server_default="false")
            )
        if not _column_exists("policies", "contexts"):
            batch_op.add_column(sa.Column("contexts", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("policies", schema=None) as batch_op:
        if _column_exists("policies", "contexts"):
            batch_op.drop_column("contexts")
        if _column_exists("policies", "llm_rejected"):
            batch_op.drop_column("llm_rejected")
        if _column_exists("policies", "needs_review"):
            batch_op.drop_column("needs_review")
        if _column_exists("policies", "category"):
            batch_op.drop_column("category")
        if _column_exists("policies", "scores"):
            batch_op.drop_column("scores")
