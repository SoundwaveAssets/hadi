"""Ce qui ne casse que sur une instance neuve : base vierge, installation non terminée."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.orchestration.queue import QueueWorker


def test_la_sonde_de_vie_repond_avant_toute_installation(client: TestClient):
    """La sonde de vie ne dépend pas de l'état de l'installation."""
    live = client.get("/api/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"


def test_les_tables_de_la_file_se_creent_sur_une_base_vierge():
    """`apply_schema` exige une application procrastinate ouverte."""
    worker = QueueWorker()
    ordre: list[str] = []

    ouverture = MagicMock()
    ouverture.__enter__ = lambda _self: ordre.append("open") or None
    ouverture.__exit__ = lambda *_: None

    remplacement = MagicMock()
    remplacement.__enter__ = lambda _self: None
    remplacement.__exit__ = lambda *_: None

    file = MagicMock()
    file.open.return_value = ouverture
    file.replace_connector.return_value = remplacement
    file.schema_manager.apply_schema.side_effect = lambda: ordre.append("apply_schema")

    inspecteur = MagicMock()
    inspecteur.get_table_names.return_value = []

    with (
        patch("app.orchestration.queue.queue", file),
        patch("app.orchestration.queue.inspect", return_value=inspecteur),
        patch.object(QueueWorker, "_run"),
    ):
        worker._ready.set()
        worker.start("postgresql://x/y", engine=object(), concurrency=1)

    assert ordre == ["open", "apply_schema"]


@pytest.mark.parametrize("route", ["/api/health/live", "/api/health"])
def test_les_deux_sondes_existent(client: TestClient, route: str):
    assert client.get(route).status_code in (200, 503)


def test_une_base_choisie_dans_l_interface_l_emporte_sur_l_environnement(tmp_path, monkeypatch):
    """
    Sans cette priorité, le formulaire enregistre une connexion que le
    démarrage ignore : c'est ce qui le rendait sans effet sous Docker.
    """
    import json

    from app.core import database as module

    fichier = tmp_path / "db_bootstrap.json"
    monkeypatch.setattr(module, "BOOTSTRAP_FILE", fichier)
    from app.core.crypto import secret_box

    fichier.write_text(json.dumps({
        "host": "distante", "port": 5432, "user": "u",
        "password": secret_box.encrypt("p"), "dbname": "d", "chosen_by_admin": True,
    }), encoding="utf-8")

    monkeypatch.setenv("DB_HOST", "interne")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        assert "distante" in module.resolve_database_url()
        assert module.database_chosen_by_admin() is True

        # Sans la marque, l'environnement reprend la main.
        fichier.write_text(json.dumps({
            "host": "distante", "port": 5432, "user": "u",
            "password": secret_box.encrypt("p"), "dbname": "d",
        }), encoding="utf-8")
        assert "interne" in module.resolve_database_url()
        assert module.database_chosen_by_admin() is False
    finally:
        monkeypatch.delenv("DB_HOST", raising=False)
        get_settings.cache_clear()
