"""
Le schéma est tenu par Alembic : base vide -> migration initiale ; base
peuplée jamais marquée -> marquée à jour sans rien recréer ; relance -> rien.
Les migrations spécifiques à PostgreSQL ne doivent pas casser sur SQLite.
"""
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401  # les tables doivent être dans metadata pour create_all
from app.core.database import DatabaseManager


def _manager(url: str) -> DatabaseManager:
    m = DatabaseManager()
    m.engine = create_engine(url)
    return m


def test_base_vide_recoit_le_schema(tmp_path):
    url = f"sqlite:///{tmp_path / 'neuve.db'}"
    m = _manager(url)
    m._migrate(url)
    tables = set(inspect(m.engine).get_table_names())
    assert {"users", "pipelines", "audit_logs", "admin_events", "developer_profiles", "pipeline_configs", "webhook_deliveries", "alembic_version"} <= tables
    m._migrate(url)  # idempotent


def test_base_peuplee_sans_marque_est_marquee_a_jour(tmp_path):
    url = f"sqlite:///{tmp_path / 'ancienne.db'}"
    m = _manager(url)
    SQLModel.metadata.create_all(m.engine)  # schéma courant, mais sans alembic_version
    assert "alembic_version" not in inspect(m.engine).get_table_names()
    m._migrate(url)
    inspector = inspect(m.engine)
    assert "alembic_version" in inspector.get_table_names()
    assert "vcs_provider" in {c["name"] for c in inspector.get_columns("pipeline_configs")}


def test_le_garde_fou_en_ajout_seul_est_sans_effet_sur_sqlite(tmp_path):
    """
    Le déclencheur PostgreSQL (journaux en ajout seul) ne s'applique pas ici,
    et la migration doit tout de même passer : c'est ce que fait la suite à
    chaque exécution, y compris dans la CI.
    """
    url = f"sqlite:///{tmp_path / 'sqlite.db'}"
    m = _manager(url)
    m._migrate(url)
    with m.engine.connect() as connection:
        connection.execute(text("INSERT INTO admin_events (timestamp, actor, actor_role, action, target_type, entry_hash, seal_version) VALUES ('2026-01-01', 'a', 'admin', 'x', 'y', 'h', 1)"))
        connection.execute(text("DELETE FROM admin_events"))
        connection.commit()
