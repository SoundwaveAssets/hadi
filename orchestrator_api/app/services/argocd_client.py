import logging

import httpx
from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.core.polling import poll_until
from app.core.tls import context_for
from app.models.config import ToolConfig

logger = logging.getLogger(__name__)


class ArgoCDClient:
    def __init__(self, session: Session):
        self.config = session.exec(select(ToolConfig)).first()
        if not self.config or not self.config.argocd_url:
            raise ValueError("La configuration de Argo CD est manquante.")

        self.api_url = self.config.argocd_url.rstrip('/')
        self.token = secret_box.decrypt(self.config.argocd_token)

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def create_application(
        self, app_name: str, repo_url: str, namespace: str, path: str = ".", target_revision: str = "main"
    ) -> None:
        """
        Crée l'Application Argo CD si elle n'existe pas déjà, jamais
        écrasée si elle existe (un admin qui l'a réglée à la main garde la
        main). Suppose que le manifeste Kubernetes (voir
        services/scaffold.py) est commité à la racine du dépôt
        (path="."), même convention que ce dépôt-ci.
        """
        url = f"{self.api_url}/api/v1/applications/{app_name}"
        async with httpx.AsyncClient(follow_redirects=True, verify=context_for(self.api_url), timeout=15.0) as client:
            existing = await client.get(url, headers=self.headers)
            if existing.status_code == 200:
                return
            payload = {
                "metadata": {"name": app_name},
                "spec": {
                    "project": "default",
                    "source": {"repoURL": repo_url, "path": path, "targetRevision": target_revision},
                    "destination": {"server": "https://kubernetes.default.svc", "namespace": namespace},
                },
            }
            response = await client.post(f"{self.api_url}/api/v1/applications", headers=self.headers, json=payload)
            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"Argo CD a refusé la création de l'Application '{app_name}' (HTTP {response.status_code}) : {response.text[:300]}"
                )

    async def sync_application(
        self, app_name: str, revision: str | None = None, timeout_seconds: int = 240, poll_interval_seconds: int = 3
    ) -> bool:
        """
        Synchronise l'application sur `revision` (le commit du dépôt de
        manifestes que deployment_flow vient d'écrire), puis attend l'issue
        RÉELLE de l'opération. Un 200 sur POST /sync dit seulement qu'Argo CD
        a accepté la demande : on interroge l'application jusqu'à ce que
        `status.operationState.phase` soit terminal (Succeeded / Failed /
        Error). Sans `revision`, Argo CD prend la tête de la branche suivie.
        """
        sync_url = f"{self.api_url}/api/v1/applications/{app_name}/sync"
        app_url = f"{self.api_url}/api/v1/applications/{app_name}"
        body = {"revision": revision} if revision else {}

        async with httpx.AsyncClient(follow_redirects=True, verify=context_for(self.api_url), timeout=15.0) as client:
            try:
                response = await client.post(sync_url, headers=self.headers, json=body)
            except Exception as e:
                logger.error(f"Impossible de joindre Argo CD : {e}")
                return False

            if response.status_code != 200:
                logger.error(f"Erreur Argo CD ({response.status_code}): {response.text}")
                return False

            logger.info(f"Synchronisation Argo CD déclenchée pour {app_name}, attente de l'issue réelle...")
            return await self._wait_for_sync_result(client, app_name, app_url, timeout_seconds, poll_interval_seconds)

    async def _get_application(self, client: httpx.AsyncClient, app_url: str) -> dict | None:
        """None tant qu'Argo CD ne répond pas 200 : le sondage continue."""
        response = await client.get(app_url, headers=self.headers)
        return response.json() if response.status_code == 200 else None

    async def _wait_for_sync_result(
        self,
        client: httpx.AsyncClient,
        app_name: str,
        app_url: str,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> bool:
        async def probe() -> bool | None:
            data = await self._get_application(client, app_url)
            if not data:
                return None
            operation = (data.get("status") or {}).get("operationState") or {}
            phase = operation.get("phase")
            if phase == "Succeeded":
                logger.info(f"Synchronisation Argo CD réussie pour {app_name}.")
                return True
            if phase in ("Failed", "Error"):
                logger.error(f"Synchronisation Argo CD en échec ({phase}) pour {app_name} : {operation.get('message', '')}")
                return False
            return None  # "Running" ou opération pas encore prise en compte

        try:
            synced = await poll_until(probe, timeout=timeout_seconds, interval=poll_interval_seconds)
        except Exception as e:
            logger.warning(f"Argo CD injoignable pendant l'attente de synchronisation de {app_name} : {e}")
            return False
        if synced is None:
            logger.warning(f"Délai d'attente dépassé pour la synchronisation Argo CD de {app_name}.")
        return bool(synced)

    async def wait_for_image(
        self, app_name: str, image_ref: str, timeout_seconds: int = 300, poll_interval_seconds: int = 5
    ) -> bool:
        """
        Preuve de déploiement : `status.summary.images` liste les images
        que les ressources vivantes de l'application référencent. Tant que
        `image_ref` (nom:sha) n'y figure pas, rien ne tourne encore avec ce
        commit, quoi qu'ait dit la synchronisation. On compare sur la fin de
        la référence : le manifeste porte le registre en préfixe, pas nous.
        """
        app_url = f"{self.api_url}/api/v1/applications/{app_name}"

        async with httpx.AsyncClient(follow_redirects=True, verify=context_for(self.api_url), timeout=15.0) as client:

            async def probe() -> bool | None:
                data = await self._get_application(client, app_url)
                images = (((data or {}).get("status") or {}).get("summary") or {}).get("images") or []
                return True if any(img == image_ref or img.endswith("/" + image_ref) for img in images) else None

            try:
                running = await poll_until(probe, timeout=timeout_seconds, interval=poll_interval_seconds)
            except Exception as e:
                logger.warning(f"Argo CD injoignable pendant la vérification d'image de {app_name} : {e}")
                return False
        if not running:
            logger.warning(f"Argo CD : {image_ref} n'apparaît pas dans les images de {app_name} après {timeout_seconds}s.")
        return bool(running)