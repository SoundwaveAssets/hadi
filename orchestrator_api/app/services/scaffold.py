"""
Fichiers de départ pour un dépôt enregistré : le Jenkinsfile (construit et
pousse l'image taguée par le commit, jamais 'latest', et s'arrête à la
vérification de sécurité tant que Hadi n'a pas tranché) et le
manifeste Kubernetes (valide tel quel, tag `RELEASE_TAG` remplacé par le SHA
approuvé à chaque déploiement, voir domain/manifest.py).

Le texte vit dans app/templates ; ici, seulement le contexte.
"""
from app.config import get_settings
from app.core.templates import render
from app.models.pipeline_config import PipelineConfig
from app.services.pipeline_config import resolve_sonarqube_key

DEFAULT_CONTAINER_PORT = 8080


def generate_jenkinsfile(config: PipelineConfig, sonarqube_url: str | None) -> str:
    return render(
        "Jenkinsfile.j2",
        repository=config.repository,
        sonar_key=resolve_sonarqube_key(config, config.repository),
        sonar_host=sonarqube_url or "<A_ADAPTER : URL du serveur SonarQube>",
        # ORCHESTRATOR_PUBLIC_URL : l'URL vue depuis l'agent Jenkins, jamais
        # host.docker.internal codé en dur (n'existe que sous Docker Desktop).
        orchestrator_url=get_settings().public_url,
    )


def generate_application_yaml(config: PipelineConfig) -> str:
    return render(
        "application.yaml.j2",
        name=config.repository,
        namespace=config.k8s_namespace or "default",
        image=config.docker_image_name or config.repository,
        port=DEFAULT_CONTAINER_PORT,
    )
