"""
Importer ce paquet enregistre toutes les tables dans SQLModel.metadata :
c'est le seul endroit qui doit connaître la liste complète des modèles
(Alembic, tests, vérifications de schéma).
"""
from app.models import (  # noqa: F401
    admin_event,
    api_token,
    audit,
    compliance_policy,
    config,
    developer_profile,
    forge_identity,
    module_state,
    notification_config,
    pipeline,
    pipeline_config,
    system,
    user,
    webhook_delivery,
)
