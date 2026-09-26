"""Journaux en ajout seul au niveau de la base

Revision ID: e5a2c8b3f107
Revises: d4f1a7c9e2b5
Create Date: 2026-09-22 15:00:00.000000

Le sceau HMAC (domain/audit_chain.py) *détecte* une altération faite hors de
l'API ; ce déclencheur la *refuse*. Un UPDATE, un DELETE ou un TRUNCATE sur
un journal échoue, qu'il vienne d'un psql ouvert par erreur ou d'un accès direct à la
base. Ce n'est pas une protection absolue (le propriétaire de la table peut
retirer le déclencheur), c'est une barrière de plus : voir le README pour
faire tourner l'application avec un rôle qui n'est pas propriétaire.

PostgreSQL uniquement : les tests tournent sur SQLite, où la question ne se
pose pas (pas de second client concurrent).

Une migration future qui doit réécrire un journal retire le déclencheur, fait
son UPDATE, puis le recrée : voir `_create` / `_drop` ci-dessous.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "e5a2c8b3f107"
down_revision: str | None = "d4f1a7c9e2b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOURNALS = ("audit_logs", "admin_events")

_FUNCTION = """
CREATE OR REPLACE FUNCTION hadi_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Le journal % est en ajout seul : ni UPDATE, ni DELETE, ni TRUNCATE.', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def _postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgresql():
        return
    op.execute(_FUNCTION)
    for table in JOURNALS:
        # TRUNCATE fait partie de la liste : sans lui, tout le garde-fou se
        # contourne en une commande, sans laisser une ligne derrière soi.
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION hadi_append_only()"
        )


def downgrade() -> None:
    if not _postgresql():
        return
    for table in JOURNALS:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS hadi_append_only()")
