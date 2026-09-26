"""
Tests de connexion et santé des outils intégrés (Jenkins, SonarQube, Argo CD,
forges) : ce que la page Intégrations et la page Monitoring affichent. Ici
les appels réseau ; les routes ne font que passer les paramètres.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from sqlmodel import Session, select

from app.ai import get_profile_stats
from app.core.crypto import secret_box
from app.core.tls import context_for
from app.models.config import ToolConfig
from app.models.pipeline_config import PipelineConfig
from app.providers import PROVIDERS, provider_from_fields
from app.providers.forges import auth_result

PINGABLE_TOOLS = ("gitea", "github", "gitlab", "jenkins", "sonarqube", "argocd")


def same_origin(url: str, saved: str | None) -> bool:
    """Même schéma, hôte et port : le seul cas où réutiliser un secret enregistré est légitime."""
    if not url or not saved:
        return False
    a, b = urlsplit(url.strip()), urlsplit(saved.strip())
    return (a.scheme.lower(), a.hostname, a.port) == (b.scheme.lower(), b.hostname, b.port)


#: Fragments trouvés dans les erreurs de certificat, en anglais comme dans les
#: messages localisés de Windows : sans eux, un problème de certificat était
#: annoncé comme « connexion refusée », et l'exploitant cherchait au mauvais endroit.
_CERTIFICATE_HINTS = (
    "CERTIFICATE_VERIFY_FAILED",
    "certificate verify failed",
    "self signed certificate",
    "certificat",
    "certificate",
)


def _is_certificate_error(text: str) -> bool:
    return any(hint.lower() in text.lower() for hint in _CERTIFICATE_HINTS)


def describe_connection_error(url: str, error: Exception) -> str:
    """
    Traduit les erreurs réseau les plus fréquentes en message actionnable.
    Constaté contre un SonarQube local : il sert du HTTP simple sur 9000, et
    une requête https:// produit WRONG_VERSION_NUMBER, qui ressemble à un
    problème réseau alors que c'est juste le mauvais schéma d'URL.
    """
    text = str(error)
    if "WRONG_VERSION_NUMBER" in text and url.lower().startswith("https://"):
        return (
            "Erreur TLS : le serveur ne semble pas parler HTTPS sur cette adresse. "
            "Beaucoup d'installations locales (SonarQube, Jenkins...) servent du HTTP simple par défaut : "
            f"essayez http://{url.split('://', 1)[-1]} au lieu de https://."
        )
    if _is_certificate_error(text):
        hote = urlsplit(url).netloc or url
        return (
            "Erreur TLS : le certificat de ce serveur n'est pas reconnu (auto-signé, expiré, ou nom qui ne "
            "correspond pas à l'adresse). C'est le cas courant d'un Argo CD déployé dans un cluster. "
            "Importez son certificat dans le magasin du système, ou déclarez cet hôte comme non vérifié : "
            f"ORCHESTRATOR_TLS_SKIP_VERIFY_HOSTS={hote}."
        )
    if isinstance(error, httpx.ConnectTimeout):
        return f"Délai dépassé en tentant de joindre {url}, le serveur ne répond pas."
    if isinstance(error, httpx.ConnectError):
        return f"Connexion refusée ou hôte injoignable : vérifiez l'adresse et le port de {url}."
    return f"Injoignable : {error}"


def _client(url: str) -> httpx.AsyncClient:
    # follow_redirects : beaucoup d'installations locales (Argo CD en tête)
    # répondent sur leur port HTTP par une redirection 307 vers HTTPS ; sans
    # la suivre, on ne voit jamais le vrai code applicatif.
    return httpx.AsyncClient(timeout=6.0, follow_redirects=True, verify=context_for(url))


async def test_jenkins(url: str, user: str | None, token: str | None) -> dict:
    auth = (user, token) if user and token else None
    async with _client(url) as client:
        response = await client.get(f"{url.rstrip('/')}/api/json", auth=auth)
    return auth_result(response.status_code, authenticated=bool(auth))


async def test_sonarqube(url: str, token: str | None) -> dict:
    auth = (token, "") if token else None
    async with _client(url) as client:
        response = await client.get(f"{url.rstrip('/')}/api/authentication/validate", auth=auth)
    if response.status_code != 200:
        return auth_result(response.status_code, authenticated=bool(auth))
    valid = response.json().get("valid")
    if valid is True:
        return {"reachable": True, "code": "auth_ok", "message": "Joignable, identifiants acceptés."}
    if valid is False:
        return {"reachable": True, "code": "auth_refused", "message": "Joignable, identifiants refusés."}
    return {"reachable": True, "code": "no_auth", "message": "Joignable, sans identifiants."}


async def test_argocd(url: str, token: str | None) -> dict:
    base = url.rstrip("/")
    async with _client(url) as client:
        # /api/version répond sans authentification avec une clé "Version" :
        # on vérifie que c'est Argo CD avant de lire un 401/403, sinon un
        # SonarQube sur le même port passe pour "Argo CD, jeton refusé".
        version_response = await client.get(f"{base}/api/version")
        try:
            looks_like_argocd = version_response.status_code == 200 and "Version" in version_response.json()
        except ValueError:  # corps non-JSON
            looks_like_argocd = False
        if not looks_like_argocd:
            return {
                "reachable": False,
                "code": "not_argocd",
                "message": "Un serveur répond à cette adresse mais ne ressemble pas à Argo CD "
                "(vérifiez le port : Argo CD écoute par défaut sur 8080, pas 9000 qui est le "
                "port par défaut de SonarQube).",
            }
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = await client.get(f"{base}/api/v1/applications", params={"fields": "items.metadata.name"}, headers=headers)
    return auth_result(response.status_code, authenticated=bool(token))


async def test_tool(tool: str, url: str, user: str | None, token: str | None) -> dict:
    """Teste un outil avec les identifiants donnés. Lève ValueError pour un outil inconnu."""
    try:
        if tool in PROVIDERS:
            return await provider_from_fields(tool, url, token).test_connection()
        if tool == "jenkins":
            return await test_jenkins(url, user, token)
        if tool == "sonarqube":
            return await test_sonarqube(url, token)
        if tool == "argocd":
            return await test_argocd(url, token)
    except Exception as e:
        return {"reachable": False, "code": "network", "message": describe_connection_error(url, e)}
    raise ValueError(f"Outil inconnu : {tool}")


async def _check(db: Session, tool: str, base_url: str | None, probe_url: str | None) -> dict:
    """
    État d'une intégration, identifiants compris quand ils existent.

    Un simple GET sans jeton laissait une tuile au vert avec un jeton révoqué
    ou absent : la panne ne se découvrait qu'au push suivant, sur une
    passerelle dont c'est justement le rôle d'éviter ça. On rejoue donc le
    même test que le bouton « Tester », avec les identifiants enregistrés.
    """
    if not probe_url:
        return {"configured": False, "reachable": None}
    user, token = _saved_credentials(db, tool)
    if token is None or not base_url:
        # Pas de jeton enregistré pour cet outil : l'atteignabilité est tout
        # ce qu'on peut affirmer, et le résultat le dit.
        result = await ping(probe_url)
        result["authenticated"] = None
        return result
    try:
        result = await test_tool(tool, base_url, user, token)
    except ValueError:
        return await ping(probe_url)
    code = result.get("code")
    return {
        "configured": True,
        "reachable": bool(result.get("reachable")),
        # None = aucun identifiant n'a été présenté, donc rien à conclure.
        "authenticated": {"auth_ok": True, "auth_refused": False}.get(code),
        "message": result.get("message"),
        "code": code,
    }


def _saved_credentials(db: Session, tool: str) -> tuple[str | None, str | None]:
    """Identifiants enregistrés d'un outil : déchiffrés en mémoire, jamais renvoyés."""
    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    if not config:
        return None, None
    raw = getattr(config, f"{tool}_token", None)
    user = getattr(config, f"{tool}_user", None)
    if not raw:
        return user, None
    try:
        return user, secret_box.decrypt(raw)
    except Exception:  # noqa: BLE001 - clé changée, valeur corrompue : on retombe sur le ping
        return user, None


async def ping(url: str | None) -> dict:
    """Simple atteignabilité HTTP, pas une validation d'authentification."""
    if not url:
        return {"configured": False, "reachable": None}
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, verify=context_for(url)) as client:
            response = await client.get(url)
        return {"configured": True, "reachable": response.status_code < 500}
    except Exception as e:
        return {"configured": True, "reachable": False, "error": str(e)}


def _base_urls(config: ToolConfig) -> dict[str, str | None]:
    """URL de base de chaque outil, celle que ses clients savent compléter eux-mêmes."""
    return {
        "gitea": config.gitea_url,
        "github": config.github_url or "https://api.github.com",
        "gitlab": config.gitlab_url or "https://gitlab.com",
        "jenkins": config.jenkins_url,
        "sonarqube": config.sonarqube_url,
        "argocd": config.argocd_url,
    }


def _health_urls(config: ToolConfig) -> dict[str, str | None]:
    return {
        "gitea": f"{config.gitea_url.rstrip('/')}/api/v1/version" if config.gitea_url else None,
        "github": f"{(config.github_url or 'https://api.github.com').rstrip('/')}/" if config.github_token else None,
        "gitlab": f"{(config.gitlab_url or 'https://gitlab.com').rstrip('/')}/api/v4/version" if config.gitlab_token else None,
        "jenkins": config.jenkins_url,
        "sonarqube": config.sonarqube_url,
        "argocd": config.argocd_url,
    }


async def integrations_health(db: Session) -> dict[str, dict]:
    """
    Atteignabilité de chaque outil, pour Intégrations et Monitoring. La base
    est forcément joignable puisque cette fonction tourne sur une session
    ouverte dessus. Le Moteur IA n'est pas pingé, c'est une bibliothèque
    interne : son indicateur reflète ce qu'il a appris.
    """
    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    urls = _health_urls(config) if config else dict.fromkeys(PINGABLE_TOOLS)
    base_urls = _base_urls(config) if config else {}

    results: dict[str, dict] = {"database": {"configured": True, "reachable": True}}
    for tool, probe_url in urls.items():
        # `probe_url` porte le chemin de sonde anonyme (…/api/v1/version) ;
        # un test authentifié, lui, part de l'URL de base de l'outil, sinon le
        # client reconstruit son chemin par-dessus et interroge une page qui
        # n'existe pas.
        results[tool] = await _check(db, tool, base_urls.get(tool), probe_url)

    pipelines = db.exec(select(PipelineConfig)).all()
    active = sum(1 for p in pipelines if p.is_active)
    results["gitea"]["message"] = f"{active} pipeline(s) actif(s) sur {len(pipelines)} enregistré(s)."

    stats = get_profile_stats(db)
    results["ai"] = {
        "configured": True,
        "reachable": True,
        "message": f"{stats['developer_count']} profil(s) de développeur appris "
        f"sur {stats['total_pushs_observed']} push(s) observé(s).",
    }
    return results
