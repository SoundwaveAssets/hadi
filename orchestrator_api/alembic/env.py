"""
Environnement Alembic. L'URL vient, dans l'ordre : de l'appelant en code
(core/database.py au démarrage), de DATABASE_URL, des variables DB_* de
Settings, sinon du fichier de bootstrap chiffré écrit par l'assistant.
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401  # enregistre toutes les tables dans metadata
from alembic import context

config = context.config
if config.config_file_name is not None:
    # Les migrations tournent aussi au démarrage de l'API : sans
    # disable_existing_loggers=False, fileConfig éteint tous les loggers déjà
    # créés et l'application cesse de journaliser après la première migration.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def include_object(objet, nom, type_, reflechi, comparaison) -> bool:
    """
    Écarte les tables de la file de travail, créées et migrées par
    procrastinate lui-même. Sans ce filtre, une autogénération produit une
    migration qui les SUPPRIME.
    """
    if type_ == "table" and (nom or "").startswith("procrastinate_"):
        return False
    if type_ == "index" and getattr(getattr(objet, "table", None), "name", "").startswith("procrastinate_"):
        return False
    return True


def _database_url() -> str:
    given = config.get_main_option("sqlalchemy.url")
    if given:
        return given
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from app.core.database import resolve_database_url

    url = resolve_database_url()
    if not url:
        raise RuntimeError("Aucune base configurée : DATABASE_URL, DB_HOST ou l'assistant d'installation.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
