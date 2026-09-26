import logging
from collections.abc import Awaitable, Callable
from xml.sax.saxutils import escape as xml_escape

import httpx
from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.core.polling import poll_until
from app.core.tls import context_for
from app.models.config import ToolConfig

logger = logging.getLogger(__name__)


class JenkinsClient:
    """
    Déclenche et suit un build Jenkins via l'API REST classique de Jenkins :
    récupération d'un crumb CSRF, POST sur le job, suivi de l'item de file
    d'attente jusqu'à l'obtention d'un numéro de build, puis attente de la
    fin de ce build.
    """

    def __init__(self, session: Session):
        self.config = session.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
        if not self.config or not self.config.jenkins_url:
            raise ValueError("La configuration de Jenkins est manquante.")

        self.base_url = self.config.jenkins_url.rstrip("/")
        self.user = self.config.jenkins_user
        self.token = secret_box.decrypt(self.config.jenkins_token)
        self.auth = (self.user, self.token) if self.user and self.token else None

    async def _get_crumb(self, client: httpx.AsyncClient) -> dict:
        """Jenkins exige un jeton CSRF pour toute requête POST si la protection est activée."""
        try:
            response = await client.get(f"{self.base_url}/crumbIssuer/api/json", auth=self.auth)
            if response.status_code == 200:
                data = response.json()
                return {data["crumbRequestField"]: data["crumb"]}
        except Exception:
            pass
        return {}

    async def trigger_build_and_wait(
        self,
        job_name: str,
        commit_hash: str,
        timeout_seconds: int = 600,
        poll_interval_seconds: int = 3,
        wait_for_stage: str | None = "Build & Test",
        on_build_number: Callable[[int], Awaitable[None]] | None = None,
    ) -> dict:
        """
        Déclenche le job et attend `wait_for_stage` (par défaut "Build & Test"),
        pas le job entier : la suite du Jenkinsfile attend elle-même la
        décision, attendre le job serait un verrou mortel. `None` attend le
        job entier (déploiement, la décision est déjà prise).
        `on_build_number` est appelé dès que le numéro est connu, pour que la
        page de détail ne dise pas "aucun build" pendant plusieurs minutes.
        """
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            headers = await self._get_crumb(client)

            trigger_response = await client.post(
                f"{self.base_url}/job/{job_name}/buildWithParameters",
                params={"COMMIT_HASH": commit_hash},
                headers=headers,
                auth=self.auth,
            )
            # Pas de repli sur /build sans paramètre : un job qui refuse
            # COMMIT_HASH construirait la tête de branche, pas ce commit, et
            # se ferait passer pour lui à toutes les étapes suivantes.
            if trigger_response.status_code not in (200, 201):
                logger.error(
                    f"Jenkins a refusé le déclenchement paramétré de '{job_name}' "
                    f"(HTTP {trigger_response.status_code}) : le job doit déclarer le paramètre COMMIT_HASH."
                )
                return {"success": False, "build_number": None}

            queue_url = trigger_response.headers.get("Location")
            if not queue_url:
                return {"success": False, "build_number": None}

            build_number = await self._wait_for_build_number(client, queue_url, timeout_seconds, poll_interval_seconds)
            if build_number is None:
                return {"success": False, "build_number": None}

            if on_build_number:
                await on_build_number(build_number)

            if wait_for_stage:
                success = await self._wait_for_stage_result(
                    client, job_name, build_number, wait_for_stage, timeout_seconds, poll_interval_seconds
                )
            else:
                success = await self._wait_for_build_result(
                    client, job_name, build_number, timeout_seconds, poll_interval_seconds
                )
            return {"success": success, "build_number": build_number}

    async def get_job_status(self, job_name: str, build_number: int) -> dict:
        """Instantané rapide {"building": bool, "result": str | None} d'un build déjà déclenché."""
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            response = await client.get(f"{self.base_url}/job/{job_name}/{build_number}/api/json", auth=self.auth)
            if response.status_code != 200:
                return {"building": False, "result": None}
            data = response.json()
            return {"building": bool(data.get("building")), "result": data.get("result")}

    async def wait_for_build_completion(
        self, job_name: str, build_number: int, timeout_seconds: int = 600, poll_interval_seconds: int = 3
    ) -> bool:
        """Attend la fin d'un build déjà déclenché (déploiement après AUTO_AUTH)."""
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            return await self._wait_for_build_result(
                client, job_name, build_number, timeout_seconds, poll_interval_seconds
            )

    async def get_console_text(self, job_name: str, build_number: int) -> str:
        """Récupère la sortie console brute d'un build déjà terminé."""
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            response = await client.get(
                f"{self.base_url}/job/{job_name}/{build_number}/consoleText", auth=self.auth
            )
            if response.status_code == 200:
                return response.text
            return f"[Console Jenkins indisponible : HTTP {response.status_code}]"

    async def list_credentials(self) -> list[dict]:
        """
        Identifiants (jamais les secrets eux-mêmes) des credentials déjà
        enregistrés dans Jenkins (Manage Jenkins > Credentials, domaine
        global), pour peupler un menu déroulant côté Dashboard plutôt que de
        faire taper un identifiant à la main lors de l'enregistrement d'un
        pipeline (voir routes_config.py).
        """
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            response = await client.get(
                f"{self.base_url}/credentials/store/system/domain/_/api/json",
                params={"tree": "credentials[id,description,typeName]"},
                auth=self.auth,
            )
            if response.status_code != 200:
                return []
            return response.json().get("credentials", [])

    async def create_or_update_pipeline_job(
        self, job_name: str, git_repo_url: str, credentials_id: str | None, description: str = ""
    ) -> None:
        """
        Crée ou reconfigure un job "Pipeline script from SCM" sur `git_repo_url`,
        Jenkinsfile à la racine. Lève si Jenkins refuse.
        """
        # Échappement obligatoire : ces valeurs viennent d'un formulaire, et
        # un `</url>` injecté écrit une configuration de job que Jenkins exécute.
        safe_url = xml_escape(git_repo_url)
        safe_description = xml_escape(description)
        credentials_xml = (
            f"<credentialsId>{xml_escape(credentials_id)}</credentialsId>" if credentials_id else ""
        )
        config_xml = f"""<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>{safe_description}</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
    <scm class="hudson.plugins.git.GitSCM" plugin="git">
      <configVersion>2</configVersion>
      <userRemoteConfigs>
        <hudson.plugins.git.UserRemoteConfig>
          <url>{safe_url}</url>
          {credentials_xml}
        </hudson.plugins.git.UserRemoteConfig>
      </userRemoteConfigs>
      <branches>
        <hudson.plugins.git.BranchSpec>
          <name>*/main</name>
        </hudson.plugins.git.BranchSpec>
      </branches>
      <doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations>
      <submoduleCfg class="empty-list"/>
      <extensions/>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
    <lightweight>true</lightweight>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>
"""
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            headers = await self._get_crumb(client)
            headers["Content-Type"] = "application/xml"

            exists_response = await client.get(f"{self.base_url}/job/{job_name}/api/json", auth=self.auth)
            if exists_response.status_code == 200:
                response = await client.post(
                    f"{self.base_url}/job/{job_name}/config.xml", headers=headers, auth=self.auth, content=config_xml
                )
            else:
                response = await client.post(
                    f"{self.base_url}/createItem",
                    params={"name": job_name},
                    headers=headers,
                    auth=self.auth,
                    content=config_xml,
                )
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Jenkins a refusé la création/mise à jour du job '{job_name}' (HTTP {response.status_code}) : {response.text[:300]}")

    async def get_stages(self, job_name: str, build_number: int) -> list[dict]:
        """
        Détail des étapes du Jenkinsfile (Checkout, Build & Test, Analyse
        SonarQube, ...) pour ce build précis, via l'API Workflow native de
        Jenkins (wfapi), la même donnée qui alimente sa propre vue "Stage
        View"/Blue Ocean, réutilisée ici pour l'afficher dans le Dashboard.
        Renvoie une liste vide si l'API est indisponible plutôt que de faire
        échouer toute la page de détail pour un simple visuel additionnel.
        """
        async with httpx.AsyncClient(timeout=15.0, verify=context_for(self.base_url)) as client:
            response = await client.get(
                f"{self.base_url}/job/{job_name}/{build_number}/wfapi/describe", auth=self.auth
            )
            if response.status_code != 200:
                return []
            data = response.json()
            return [
                {
                    "name": s.get("name"),
                    "status": s.get("status"),
                    "duration_ms": s.get("durationMillis"),
                }
                for s in data.get("stages", [])
            ]

    async def _get_json(self, client: httpx.AsyncClient, url: str) -> dict | None:
        """None tant que Jenkins ne répond pas 200 : le sondage continue."""
        response = await client.get(url, auth=self.auth)
        return response.json() if response.status_code == 200 else None

    async def _wait_for_build_number(
        self, client: httpx.AsyncClient, queue_url: str, timeout_seconds: int, poll_interval_seconds: int
    ) -> int | None:
        queue_api_url = queue_url.rstrip("/") + "/api/json"

        async def probe() -> int | None:
            data = await self._get_json(client, queue_api_url)
            if not data:
                return None
            if data.get("cancelled"):
                raise _BuildCancelled
            return (data.get("executable") or {}).get("number")

        try:
            return await poll_until(probe, timeout=timeout_seconds, interval=poll_interval_seconds)
        except _BuildCancelled:
            return None

    async def _wait_for_build_result(
        self,
        client: httpx.AsyncClient,
        job_name: str,
        build_number: int,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> bool:
        build_api_url = f"{self.base_url}/job/{job_name}/{build_number}/api/json"

        async def probe() -> bool | None:
            data = await self._get_json(client, build_api_url)
            if not data or data.get("building"):
                return None
            return data.get("result") == "SUCCESS"

        return bool(await poll_until(probe, timeout=timeout_seconds, interval=poll_interval_seconds))

    async def _wait_for_stage_result(
        self,
        client: httpx.AsyncClient,
        job_name: str,
        build_number: int,
        stage_name: str,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> bool:
        """
        Attend qu'une étape précise atteigne un état terminal, pas le job
        entier, qui continue après (voir trigger_build_and_wait). Utilise la
        même API Workflow (wfapi) que get_stages().
        """
        describe_url = f"{self.base_url}/job/{job_name}/{build_number}/wfapi/describe"

        async def probe() -> bool | None:
            data = await self._get_json(client, describe_url)
            if not data:
                return None
            stage = next((s for s in data.get("stages", []) if s.get("name") == stage_name), None)
            if stage and stage.get("status") not in ("IN_PROGRESS", "NOT_EXECUTED", None):
                return stage["status"] == "SUCCESS"
            # Job terminé sans avoir exécuté l'étape (ex. Checkout en échec).
            # Tester une valeur terminale explicite : au premier sondage,
            # status peut être absent, ce qui déclarait le build en échec
            # deux secondes après son lancement.
            if stage is None and data.get("status") in ("SUCCESS", "FAILED", "ABORTED", "UNSTABLE"):
                return False
            return None

        return bool(await poll_until(probe, timeout=timeout_seconds, interval=poll_interval_seconds))


class _BuildCancelled(Exception):
    """L'item de file d'attente a été annulé avant de produire un build."""
