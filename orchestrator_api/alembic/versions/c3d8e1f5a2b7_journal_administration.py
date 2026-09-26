"""Journal des actions d'administration

Revision ID: c3d8e1f5a2b7
Revises: b7c2d9e4f1a3
Create Date: 2026-09-21 21:00:00.000000

`admin_events` : seconde chaîne d'intégrité HMAC (models/admin_event.py),
distincte du journal des décisions, pour les comptes, intégrations, modules,
politiques, pipelines enregistrés et connexions.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d8e1f5a2b7"
down_revision: str | None = "b7c2d9e4f1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("target_label", sa.String(), nullable=True),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("previous_hash", sa.String(), nullable=True),
        sa.Column("entry_hash", sa.String(), nullable=False),
        sa.Column("seal_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_admin_events_actor", "admin_events", ["actor"])
    op.create_index("ix_admin_events_action", "admin_events", ["action"])


def downgrade() -> None:
    op.drop_index("ix_admin_events_action", table_name="admin_events")
    op.drop_index("ix_admin_events_actor", table_name="admin_events")
    op.drop_table("admin_events")
