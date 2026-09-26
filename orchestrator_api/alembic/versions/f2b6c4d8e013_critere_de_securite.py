"""Critère de sécurité du Moteur de décision

Revision ID: f2b6c4d8e013
Revises: e5a2c8b3f107
Create Date: 2026-09-22 18:00:00.000000

Le moteur jugeait la sécurité d'un commit sur le nombre TOTAL de
vulnérabilités du projet : un dépôt qui traîne de la dette bloquait tous ses
pushs, y compris ceux qui la réduisaient. Le critère devient réglable et vaut
désormais « code neuf » par défaut (voir domain/decision.py).

- tool_configurations.security_criterion : réglage global.
- pipeline_configs.security_criterion : surcharge par dépôt (NULL = hérite).
- audit_logs.security_criterion : ce qui a réellement tranché, scellé (v3).

Les instances existantes reçoivent explicitement "total" : leur
comportement ne change pas du jour au lendemain à cause d'une mise à jour.
C'est à l'administrateur de basculer sur le code neuf en connaissance de cause.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b6c4d8e013"
down_revision: str | None = "e5a2c8b3f107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tool_configurations") as batch:
        batch.add_column(sa.Column("security_criterion", sa.String(), nullable=False, server_default="new_code"))
    with op.batch_alter_table("pipeline_configs") as batch:
        batch.add_column(sa.Column("security_criterion", sa.String(), nullable=True))
    with op.batch_alter_table("audit_logs") as batch:
        batch.add_column(sa.Column("security_criterion", sa.String(), nullable=True))

    # Une instance déjà installée garde son comportement : elle décidait sur
    # la dette totale, elle continue, jusqu'à ce qu'un administrateur change.
    op.execute("UPDATE tool_configurations SET security_criterion = 'total' WHERE id = 1")


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_column("security_criterion")
    with op.batch_alter_table("pipeline_configs") as batch:
        batch.drop_column("security_criterion")
    with op.batch_alter_table("tool_configurations") as batch:
        batch.drop_column("security_criterion")
