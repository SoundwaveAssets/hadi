"""`DEPLOYED` exige que l'application tourne, pas seulement qu'elle déclare l'image."""
import pytest

from app.services.argocd_client import ArgoCDClient


def _client(monkeypatch, etat: dict) -> ArgoCDClient:
    client = ArgoCDClient.__new__(ArgoCDClient)
    client.api_url = "https://argocd.exemple"
    client.headers = {}

    async def _get_application(_self, _client, _url):
        return {"status": etat}

    monkeypatch.setattr(ArgoCDClient, "_get_application", _get_application)
    return client


IMAGE = "demo:abc123"


@pytest.mark.anyio
async def test_image_declaree_mais_application_degradee(monkeypatch):
    """Un pod en ImagePullBackOff laisse l'image dans le résumé de l'application."""
    client = _client(monkeypatch, {"summary": {"images": [f"registre/{IMAGE}"]}, "health": {"status": "Degraded"}})
    assert await client.wait_for_image("demo", IMAGE, timeout_seconds=1, poll_interval_seconds=1) is False


@pytest.mark.anyio
async def test_image_declaree_et_application_saine(monkeypatch):
    client = _client(monkeypatch, {"summary": {"images": [f"registre/{IMAGE}"]}, "health": {"status": "Healthy"}})
    assert await client.wait_for_image("demo", IMAGE, timeout_seconds=1, poll_interval_seconds=1) is True


@pytest.mark.anyio
async def test_autre_image_saine(monkeypatch):
    client = _client(monkeypatch, {"summary": {"images": ["registre/demo:autre"]}, "health": {"status": "Healthy"}})
    assert await client.wait_for_image("demo", IMAGE, timeout_seconds=1, poll_interval_seconds=1) is False
