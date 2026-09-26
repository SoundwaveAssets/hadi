"""Profils comportementaux en base

Revision ID: d4f1a7c9e2b5
Revises: c3d8e1f5a2b7
Create Date: 2026-09-22 14:30:00.000000

`developer_profiles` remplace local_data/ai_profiles.json : plusieurs
répliques partagent le même profil et un conteneur qui redémarre ne réapprend
rien. Le fichier existant, s'il y en a un, est importé ici puis laissé en
place (sauvegarde) ; il n'est plus lu ensuite.
"""
import json
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "d4f1a7c9e2b5"
down_revision: str | None = "c3d8e1f5a2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _legacy_profiles() -> list[dict]:
    from app.core.secrets_store import LOCAL_DATA_DIR

    path = LOCAL_DATA_DIR / "ai_profiles.json"
    if not path.exists():
        return []
    try:
        developers = json.loads(path.read_text(encoding="utf-8")).get("developers", {})
    except (ValueError, OSError):
        return []
    now = datetime.now(timezone.utc)
    return [
        {
            "developer": name,
            "history": json.dumps(profile.get("history", [])),
            "known_files": json.dumps(profile.get("known_files", [])),
            "updated_at": now,
        }
        for name, profile in developers.items()
    ]


def upgrade() -> None:
    table = op.create_table(
        "developer_profiles",
        sa.Column("developer", sa.String(), primary_key=True),
        sa.Column("history", sa.Text(), nullable=False),
        sa.Column("known_files", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    rows = _legacy_profiles()
    if rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_table("developer_profiles")
