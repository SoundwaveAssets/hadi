"""Fichiers de départ : manifeste YAML valide, Jenkinsfile complet, aucune variable oubliée."""
import yaml

from app.models.pipeline_config import PipelineConfig
from app.services.scaffold import generate_application_yaml, generate_jenkinsfile


def _config(**overrides) -> PipelineConfig:
    values = {"repository": "boutique", "webhook_secret": "x", "created_by": "admin"}
    values.update(overrides)
    return PipelineConfig(**values)


def test_manifeste_est_du_yaml_valide_avec_deployment_et_service():
    documents = list(yaml.safe_load_all(generate_application_yaml(_config(k8s_namespace="prod", docker_image_name="shop"))))
    assert [d["kind"] for d in documents] == ["Deployment", "Service"]
    deployment, service = documents
    assert deployment["metadata"] == {
        "name": "boutique",
        "namespace": "prod",
        "labels": {"app.kubernetes.io/name": "boutique", "app.kubernetes.io/managed-by": "orchestrateur-cicd"},
    }
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "shop:RELEASE_TAG"
    assert service["spec"]["selector"] == {"app.kubernetes.io/name": "boutique"}


def test_manifeste_defauts():
    deployment = next(yaml.safe_load_all(generate_application_yaml(_config())))
    assert deployment["metadata"]["namespace"] == "default"
    assert deployment["spec"]["template"]["spec"]["containers"][0]["image"] == "boutique:RELEASE_TAG"


def test_jenkinsfile_pointe_sur_le_bon_pipeline():
    content = generate_jenkinsfile(_config(sonarqube_project_key="shop-key"), sonarqube_url="https://sonar.exemple.org")
    assert "pipeline '{}'".format("boutique") in content
    assert "-Dsonar.projectKey=shop-key" in content
    assert "-Dsonar.host.url=https://sonar.exemple.org" in content
    assert "/api/decisions/gate/boutique/$COMMIT_HASH" in content
    assert "{{" not in content and "}}" not in content
    # Les accolades Groovy sont intactes.
    assert 'docker.build("${DOCKER_IMAGE}:${params.COMMIT_HASH}")' in content


def test_jenkinsfile_sans_sonarqube_configure():
    assert "<A_ADAPTER : URL du serveur SonarQube>" in generate_jenkinsfile(_config(), sonarqube_url=None)
