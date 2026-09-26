"""Ajout de expires_at sur api_tokens

Revision ID: a1b2c3d4e5f6
Revises: 52690d3bf76c
Create Date: 2026-09-20 20:00:00.000000

Ajoute la colonne `expires_at` (TIMESTAMPTZ nullable) sur la table
`api_tokens` pour permettre l'expiration automatique des jetons API.
NULL = pas d'expiration (comportement précédent conservé).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "52690d3bf76c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_tokens", "expires_at")
