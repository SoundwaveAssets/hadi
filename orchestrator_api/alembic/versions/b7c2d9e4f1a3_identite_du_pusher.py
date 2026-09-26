"""Identité du pusher : correspondance forge -> compte, provenance scellée, sceau versionné

Revision ID: b7c2d9e4f1a3
Revises: a1b2c3d4e5f6
Create Date: 2026-09-21 18:00:00.000000

- `forge_identities` : login de forge relié à un utilisateur Hadi (par un admin).
- `pipelines.commit_author` / `pipelines.identity_source` : le nom d'auteur Git
  redevient une simple information ; `author` porte l'identité résolue.
- `audit_logs.developer_identity_source` : provenance de l'identité, scellée.
- `audit_logs.seal_version` : liste de champs scellés utilisée par chaque
  entrée ; les entrées existantes restent en version 1 et vérifiables.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c2d9e4f1a3"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forge_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "login", name="uq_forge_identities_provider_login"),
    )
    op.create_index("ix_forge_identities_user_id", "forge_identities", ["user_id"])

    with op.batch_alter_table("pipelines") as batch:
        batch.add_column(sa.Column("commit_author", sa.String(), nullable=True))
        batch.add_column(sa.Column("identity_source", sa.String(), nullable=True))

    with op.batch_alter_table("audit_logs") as batch:
        batch.add_column(sa.Column("developer_identity_source", sa.String(), nullable=True))
        batch.add_column(sa.Column("seal_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_column("seal_version")
        batch.drop_column("developer_identity_source")
    with op.batch_alter_table("pipelines") as batch:
        batch.drop_column("identity_source")
        batch.drop_column("commit_author")
    op.drop_index("ix_forge_identities_user_id", table_name="forge_identities")
    op.drop_table("forge_identities")
