"""
Journalisation : "json" pour l'ingestion (Loki, Datadog, ELK), "text" en
développement, selon LOG_FORMAT.

Les champs passés en `extra` deviennent des clés de premier niveau en JSON,
et sont ignorés en mode texte.
"""
from __future__ import annotations

import logging
import logging.config
import os


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure la journalisation globale. Appelée une seule fois au démarrage
    de l'application (app/main.py), avant tout import applicatif.

    `log_level` : niveau de journalisation (INFO, DEBUG, WARNING, ERROR, CRITICAL).
    `LOG_FORMAT` : "json" pour la production, "text" (défaut) pour le développement.
    """
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    if log_format == "json":
        _configure_json(log_level)
    else:
        _configure_text(log_level)


def _configure_text(log_level: str) -> None:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def _configure_json(log_level: str) -> None:
    try:
        from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]
    except ImportError:
        # python-json-logger absent (environnement de test minimal) : repli texte.
        _configure_text(log_level)
        return

    class _HadiJsonFormatter(jsonlogger.JsonFormatter):
        """
        Formateur JSON avec champs normalisés pour Loki/Datadog/ELK.
        Les champs `extra` passés à logger.info(..., extra={...}) apparaissent
        comme clés de premier niveau, ce qui permet des requêtes comme :
            {repository="mon-projet"} |= "Analyse"
        """

        def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict) -> None:
            super().add_fields(log_record, record, message_dict)
            # Normalisation des noms de champs pour la cohérence entre services.
            log_record["level"] = record.levelname
            log_record["logger"] = record.name
            # Suppression des doublons produits par JsonFormatter par défaut.
            log_record.pop("levelname", None)
            log_record.pop("name", None)

    handler = logging.StreamHandler()
    handler.setFormatter(
        _HadiJsonFormatter(
            fmt="%(asctime)s %(level)s %(logger)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(log_level)
    # Remplace les handlers existants pour éviter les doublons si appelé
    # plusieurs fois (tests, rechargement à chaud).
    root.handlers = [handler]

    # Silence les loggers tiers trop verbeux en production.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "procrastinate"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
