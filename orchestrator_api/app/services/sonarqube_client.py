import logging

import httpx
from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.core.polling import poll_until
from app.core.tls import context_for
from app.domain.decision import GATE_FAILED, GATE_PASSED, UNVERIFIABLE
from app.models.config import ToolConfig

logger = logging.getLogger(__name__)

#: Réponse type quand rien n'a pu être mesuré : tout est « non vérifiable »,
#: jamais zéro (voir domain/decision.py).
UNMEASURED: dict = {
    "vulnerabilities": UNVERIFIABLE,
    "new_vulnerabilities": UNVERIFIABLE,
    "bugs": UNVERIFIABLE,
    "new_bugs": UNVERIFIABLE,
    "quality_gate": None,
    "failed_gate_conditions": [],
}


class SonarQubeClient:
    def __init__(self, session: Session):
        self.config = session.exec(select(ToolConfig)).first()
        if not self.config or not self.config.sonarqube_url:
            raise ValueError("La configuration de SonarQube est manquante.")

        self.api_url = self.config.sonarqube_url.rstrip('/')
        self.token = secret_box.decrypt(self.config.sonarqube_token)
        
    # Notes A-E de SonarQube : renvoyées en interne comme "1.0".."5.0" par
    # l'API measures, reconverties en lettre ici pour ne pas faire porter
    # cette traduction au frontend.
    _RATING_LETTERS = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}

    async def ensure_project(self, project_key: str, name: str) -> None:
        """
        Crée le projet SonarQube s'il n'existe pas déjà, idempotent :
        SonarQube répond 400 "A similar key already exists" pour un projet
        déjà là (testé en direct), ce qui n'est pas une vraie erreur ici,
        juste rien à faire. Contrairement à l'auto-provisionnement Jenkins/
        Argo CD (voir routes_pipeline_configs.py), pas besoin de case à
        cocher dédiée : appeler ceci sur un projet déjà existant est sans
        risque, donc systématique à l'enregistrement d'un pipeline.
        """
        url = f"{self.api_url}/api/projects/create"
        auth = (self.token, "")
        async with httpx.AsyncClient(verify=context_for(self.api_url)) as client:
            response = await client.post(url, data={"project": project_key, "name": name}, auth=auth)
            if response.status_code == 200:
                return
            if response.status_code == 400 and "already exist" in response.text.lower():
                return
            raise RuntimeError(f"SonarQube a refusé la création du projet '{project_key}' (HTTP {response.status_code}) : {response.text[:300]}")

    async def wait_for_analysis(
        self, project_key: str, commit_hash: str, timeout_seconds: int = 600, poll_interval_seconds: int = 5
    ) -> bool:
        """
        Attend que l'analyse de CE commit soit enregistrée ET soit la plus
        récente du projet. Les deux conditions comptent : get_security_metrics
        lit l'état courant du projet, donc si une analyse plus récente (autre
        commit) est passée entre-temps, les mesures ne sont plus celles de ce
        commit. Dans les deux cas d'échec (délai dépassé, analyse dépassée),
        l'appelant doit renvoyer UNVERIFIABLE, jamais une lecture "au mieux" :
        un commit précédent propre ferait passer n'importe quoi.

        La corrélation se fait sur `revision`, que le Jenkinsfile généré
        renseigne explicitement (-Dsonar.scm.revision) : on ne dépend pas de
        l'auto-détection du scanner.
        """
        url = f"{self.api_url}/api/project_analyses/search"
        auth = (self.token, "")

        async with httpx.AsyncClient(verify=context_for(self.api_url)) as client:

            async def probe() -> bool | None:
                response = await client.get(url, params={"project": project_key, "ps": 10}, auth=auth)
                if response.status_code != 200:
                    return None
                # Triées de la plus récente à la plus ancienne par SonarQube.
                analyses = response.json().get("analyses", [])
                if analyses and analyses[0].get("revision") == commit_hash:
                    return True
                if any(a.get("revision") == commit_hash for a in analyses):
                    logger.warning(
                        f"SonarQube : l'analyse de {commit_hash[:7]} sur '{project_key}' "
                        "a été dépassée par une analyse plus récente, mesures non attribuables."
                    )
                    return False
                return None

            found = await poll_until(probe, timeout=timeout_seconds, interval=poll_interval_seconds)
        if found is None:
            logger.warning(f"SonarQube : aucune analyse pour {commit_hash[:7]} sur '{project_key}' après {timeout_seconds}s.")
        return bool(found)

    async def get_security_metrics(self, project_key: str) -> dict:
        """
        Instantané de qualité du projet : ce que le Moteur de décision lit
        (vulnérabilités du code neuf, du projet entier) et ce que la page de
        détail d'un pipeline affiche (bugs, notes, hotspots, couverture,
        duplication), en une seule requête.

        Les métriques `new_*` ne portent que sur la période de code neuf
        définie sur le projet SonarQube (version précédente, nombre de jours,
        ou date de référence). C'est ce qui permet de décider PAR COMMIT au
        lieu de sanctionner éternellement la dette d'un dépôt ancien.
        """
        url = f"{self.api_url}/api/measures/component"
        params = {
            "component": project_key,
            "metricKeys": (
                "vulnerabilities,bugs,security_rating,reliability_rating,sqale_rating,"
                "security_hotspots_reviewed,coverage,duplicated_lines_density,ncloc,"
                "new_vulnerabilities,new_bugs,new_security_rating,new_security_hotspots_reviewed,new_coverage"
            ),
        }

        # Authentification Basic HTTP (SonarQube utilise le token comme nom d'utilisateur)
        auth = (self.token, "")

        async with httpx.AsyncClient(verify=context_for(self.api_url)) as client:
            response = await client.get(url, params=params, auth=auth)

            if response.status_code == 200:
                data = response.json()
                raw = self._measures(data.get("component", {}).get("measures", []))

                def _rating(key: str) -> str | None:
                    value = raw.get(key)
                    if value is None:
                        return None
                    return self._RATING_LETTERS.get(round(float(value)))

                def _float(key: str) -> float | None:
                    value = raw.get(key)
                    return float(value) if value is not None else None

                def _int(key: str, default: int = 0) -> int:
                    value = raw.get(key)
                    return int(float(value)) if value is not None else default

                return {
                    # UNVERIFIABLE, jamais 0 : une mesure absente (projet jamais
                    # analysé, métrique dépréciée en SonarQube 10) n'est pas
                    # "zéro vulnérabilité". Avec 0, c'était un fail-open.
                    "vulnerabilities": _int("vulnerabilities", UNVERIFIABLE),
                    "new_vulnerabilities": _int("new_vulnerabilities", UNVERIFIABLE),
                    "bugs": _int("bugs", UNVERIFIABLE),
                    "new_bugs": _int("new_bugs", UNVERIFIABLE),
                    "security_rating": _rating("security_rating"),
                    "new_security_rating": _rating("new_security_rating"),
                    "reliability_rating": _rating("reliability_rating"),
                    "maintainability_rating": _rating("sqale_rating"),
                    "security_hotspots_reviewed": _float("security_hotspots_reviewed"),
                    "new_security_hotspots_reviewed": _float("new_security_hotspots_reviewed"),
                    "coverage": _float("coverage"),
                    "new_coverage": _float("new_coverage"),
                    "duplicated_lines_density": _float("duplicated_lines_density"),
                    "lines_of_code": _int("ncloc"),
                }
            else:
                logger.error(f"Erreur SonarQube ({response.status_code}): {response.text}")
                # Erreur API : non vérifiable, pas inventé (voir domain/decision.py).
                return dict(UNMEASURED)

    @staticmethod
    def _measures(measures: list[dict]) -> dict[str, str]:
        """
        Aplatit la réponse de /api/measures/component.

        Une mesure de code neuf ne porte pas de `value` : sa valeur est dans
        `period` (SonarQube 8+) ou dans `periods[0]` (versions antérieures).
        Lire uniquement `value` renvoyait donc systématiquement « absent »
        pour toutes les métriques new_*, c'est-à-dire non vérifiable.
        """
        flat: dict[str, str] = {}
        for measure in measures:
            value = measure.get("value")
            if value is None:
                periods = measure.get("periods") or []
                period = measure.get("period") or (periods[0] if periods else {})
                value = period.get("value")
            if value is not None:
                flat[measure["metric"]] = value
        return flat

    async def get_quality_gate(self, project_key: str) -> dict:
        """
        Verdict du Quality Gate du projet, avec le nom des conditions en
        échec. C'est la politique telle que les équipes la configurent déjà
        dans SonarQube : quand un pipeline choisit ce critère, Hadi ne
        réinvente pas de seuil, il lit celui de l'outil.
        """
        url = f"{self.api_url}/api/qualitygates/project_status"
        async with httpx.AsyncClient(verify=context_for(self.api_url)) as client:
            response = await client.get(url, params={"projectKey": project_key}, auth=(self.token, ""))
            if response.status_code != 200:
                logger.warning(f"Quality Gate SonarQube indisponible pour '{project_key}' (HTTP {response.status_code}).")
                return {"quality_gate": None, "failed_gate_conditions": []}

            status = response.json().get("projectStatus", {})
            verdict = status.get("status")
            failed = [
                condition.get("metricKey", "?")
                for condition in status.get("conditions", [])
                if condition.get("status") == GATE_FAILED
            ]
            return {
                "quality_gate": verdict if verdict in (GATE_PASSED, GATE_FAILED) else None,
                "failed_gate_conditions": failed,
            }