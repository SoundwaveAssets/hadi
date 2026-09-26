from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, Session, SQLModel

from app.domain.pipeline_status import PipelineStatus


class Pipeline(SQLModel, table=True):
    """Suivi d'un push reçu et de son traitement."""

    __tablename__ = "pipelines"
    # Unique sur (repository, commit_id), jamais commit_id seul : un même hash
    # peut apparaître sur plusieurs dépôts, et le bouton de test des forges
    # envoie partout le même commit factice.
    __table_args__ = (UniqueConstraint("repository", "commit_id", name="ix_pipelines_repository_commit_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)

    # Données issues du Webhook
    repository: str = Field(index=True)
    branch: str
    commit_id: str = Field(index=True)
    commit_message: str
    #: Identité résolue du pusher (domain/identity.py) : compte Hadi relié,
    #: sinon login de forge, sinon nom d'auteur Git. C'est sur elle que
    #: portent les filtres « mes pipelines ».
    author: str
    #: Nom d'auteur du commit tel quel (texte libre), pour l'affichage.
    commit_author: Optional[str] = Field(default=None)
    identity_source: Optional[str] = Field(default=None, description="mapped | forge | git-author")

    # Cycle de vie du pipeline
    #: Colonne texte (pas un type énuméré en base : ajouter un statut ne doit
    #: pas demander de migration), mais les valeurs viennent toutes de
    #: PipelineStatus, seul vocabulaire autorisé.
    status: str = Field(
        default=PipelineStatus.PENDING.value,
        description=" | ".join(s.value for s in PipelineStatus),
    )
    # Colonne explicitement TIMESTAMP WITH TIME ZONE (voir models/audit.py pour le pourquoi).
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Numéro de build Jenkins associé, pour rapatrier sa console a posteriori.
    jenkins_build_number: Optional[int] = Field(default=None)

    # Récit de l'exécution interne, accumulé étape par étape par
    # append_pipeline_log().
    execution_log: Optional[str] = Field(default=None, sa_column=Column(Text))


#: Séparateur inséré au début d'une nouvelle tentative sur le même commit.
RUN_SEPARATOR = "────────"


def start_pipeline_run(session: Session, pipeline: "Pipeline", reason: str) -> None:
    """
    Ouvre une nouvelle tentative sur un commit déjà connu.

    Les exécutions s'empilent : le récit de la précédente est la seule trace
    de ce qui a échoué. Le numéro de build reste jusqu'à ce que le nouveau
    soit connu, pour garder sa console consultable entre-temps.
    """
    pipeline.status = PipelineStatus.PENDING.value
    session.add(pipeline)
    session.commit()
    horodatage = datetime.now(timezone.utc).strftime("%d/%m %H:%M:%S")
    append_pipeline_log(session, pipeline.id, f"{RUN_SEPARATOR} Nouvelle exécution ({reason}) le {horodatage} {RUN_SEPARATOR}")


def append_pipeline_log(session: Session, pipeline_id: Optional[int], message: str) -> None:
    """Ajoute une ligne horodatée au journal d'exécution d'un pipeline."""
    if pipeline_id is None:
        return
    pipeline = session.get(Pipeline, pipeline_id)
    if not pipeline:
        return
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    pipeline.execution_log = f"{pipeline.execution_log}\n{line}" if pipeline.execution_log else line
    session.add(pipeline)
    session.commit()
