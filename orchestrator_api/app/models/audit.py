import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, Session, SQLModel, select

from app.core.audit_seal import AUDIT_KEY, read_genesis, write_genesis
from app.core.chain_lock import serialize_chain_writes
from app.domain.audit_chain import CURRENT_SEAL_VERSION, SEALED_FIELDS_BY_VERSION, seal, utc_isoformat, verify_entry


class AuditLog(SQLModel, table=True):
    """
    Table d'audit inaltérable (append-only) pour la traçabilité de toutes les décisions.

    Au-delà du simple append-only côté application, chaque entrée porte le
    hash de la précédente (`previous_hash` / `entry_hash`) : toute altération
    ou suppression rétroactive d'une ligne, y compris via un accès direct à
    la base, hors de l'API, casse la chaîne et devient détectable via
    `verify_chain_integrity`. C'est ce qui rend le journal réellement
    infalsifiable, pas seulement en théorie applicative.
    """

    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    # L'heure de l'événement est générée automatiquement à la création.
    # Colonne explicitement TIMESTAMP WITH TIME ZONE : sans ça, PostgreSQL
    # convertit silencieusement la valeur UTC vers le fuseau de la session au
    # moment de l'écriture, ce qui décale l'horodatage relu et casse le hash.
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Contexte du déclencheur
    developer_username: str
    #: Provenance de developer_username (domain/identity.py) : mapped, forge ou
    #: git-author. Absent sur les entrées dérivées (dérogations) et anciennes.
    developer_identity_source: Optional[str] = Field(default=None)
    repository_name: str
    commit_hash: str

    # Preuves ayant motivé la décision
    ai_anomaly_score: Optional[float] = Field(default=None)
    ai_explanation: Optional[str] = Field(
        default=None, description="Facteurs déclencheurs transmis par le moteur IA, jamais une décision"
    )
    sonarqube_vulnerabilities: Optional[int] = Field(
        default=None, description="Vulnérabilités du projet entier au moment de la décision"
    )
    #: Critère appliqué pour juger la sécurité (domain/decision.py) :
    #: new_code, quality_gate ou total. Scellé depuis la version 3 : sans lui,
    #: relire une décision ancienne ne dit pas ce qu'elle a réellement mesuré.
    security_criterion: Optional[str] = Field(default=None)
    # Instantané informatif pour la fiche du pipeline (bugs, notes, couverture,
    # duplication). Hors du hash de chaînage : seul ce qui a motivé la décision
    # y participe.
    sonarqube_metrics: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Résultat
    decision: str = Field(description="Ex: AUTO_AUTH, BLOCKED, WAITING_HUMAN, DEROGATION, REJECTED_INVALID_SIGNATURE")
    justification: str = Field(description="Explication de la décision (règle violée ou motif dérogation)")

    # Gouvernance Humaine (Rempli uniquement lors d'une dérogation)
    approved_by: Optional[str] = Field(default=None, description="Admin 1 ayant autorisé")
    four_eyes_approved_by: Optional[str] = Field(default=None, description="Admin 2 ayant confirmé (Prod)")

    # Une dérogation ne modifie JAMAIS l'entrée d'origine (append-only) :
    # elle s'écrit comme une nouvelle entrée qui référence celle qu'elle
    # remplace, pour que l'historique complet reste reconstituable.
    supersedes_audit_id: Optional[int] = Field(
        default=None, description="ID de l'entrée d'audit que cette dérogation remplace, le cas échéant"
    )

    # Chaînage d'intégrité (voir append_audit_log / verify_chain_integrity)
    previous_hash: Optional[str] = Field(default=None, description="Condensat de l'entrée précédente de la chaîne")
    entry_hash: str = Field(default="", description="HMAC-SHA256 de cette entrée chaînée à previous_hash")
    #: Liste de champs scellés utilisée (domain/audit_chain.py) ; une entrée se vérifie toujours avec la sienne.
    seal_version: int = Field(default=CURRENT_SEAL_VERSION)


def _sealed_fields(entry: AuditLog) -> dict:
    data = {name: getattr(entry, name) for name in SEALED_FIELDS_BY_VERSION[entry.seal_version]}
    data["timestamp"] = utc_isoformat(entry.timestamp)
    data["entry_hash"] = entry.entry_hash
    data["seal_version"] = entry.seal_version
    return data


def compute_legacy_hash(entry: AuditLog, previous_hash: Optional[str]) -> str:
    """
    Ancien condensat SHA-256 nu, conservé UNIQUEMENT pour vérifier les
    entrées écrites avant la bascule HMAC (voir core/audit_seal.py). Plus
    jamais utilisé pour écrire.
    """
    payload = {
        "timestamp": utc_isoformat(entry.timestamp),
        "developer_username": entry.developer_username,
        "repository_name": entry.repository_name,
        "commit_hash": entry.commit_hash,
        "ai_anomaly_score": entry.ai_anomaly_score,
        "ai_explanation": entry.ai_explanation,
        "sonarqube_vulnerabilities": entry.sonarqube_vulnerabilities,
        "decision": entry.decision,
        "justification": entry.justification,
        "approved_by": entry.approved_by,
        "four_eyes_approved_by": entry.four_eyes_approved_by,
        "supersedes_audit_id": entry.supersedes_audit_id,
        "previous_hash": previous_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def append_audit_log(session: Session, entry: AuditLog) -> AuditLog:
    """
    Point d'entrée unique pour écrire dans le journal : calcule le chaînage
    avant d'insérer, pour que tous les appelants produisent une chaîne
    cohérente. La première écriture après la bascule ancre la fin de
    l'ancienne chaîne SHA-256 hors de la base (audit.genesis).
    """
    serialize_chain_writes(session, "audit_logs")
    last_entry = session.exec(select(AuditLog).order_by(AuditLog.id.desc())).first()
    previous_hash = last_entry.entry_hash if last_entry else None

    if read_genesis() is None:
        write_genesis(last_entry.id if last_entry else 0, last_entry.entry_hash if last_entry else "")

    entry.previous_hash = previous_hash
    entry.seal_version = CURRENT_SEAL_VERSION
    entry.entry_hash = seal(_sealed_fields(entry), previous_hash, key=AUDIT_KEY, version=CURRENT_SEAL_VERSION)

    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def verify_chain_integrity(session: Session) -> tuple[bool, Optional[int]]:
    """
    Rejoue toute la chaîne. Les entrées jusqu'à l'ancrage (audit.genesis)
    se vérifient avec l'ancien SHA-256, la dernière d'entre elles doit en
    plus correspondre au condensat ancré ; tout ce qui suit se vérifie en
    HMAC avec la clé. Renvoie (intègre, id de la première entrée en défaut).
    """
    genesis = read_genesis()
    legacy_until = genesis["id"] if genesis else None
    entries = session.exec(select(AuditLog).order_by(AuditLog.id.asc())).all()
    previous_hash: Optional[str] = None
    for entry in entries:
        if legacy_until is not None and entry.id is not None and entry.id <= legacy_until:
            if entry.entry_hash != compute_legacy_hash(entry, previous_hash):
                return False, entry.id
            if entry.id == legacy_until and entry.entry_hash != genesis["entry_hash"]:
                return False, entry.id
        elif legacy_until is None:
            # Journal jamais scellé en HMAC (aucune écriture depuis la
            # bascule) : l'ancien algorithme est le seul applicable.
            if entry.entry_hash != compute_legacy_hash(entry, previous_hash):
                return False, entry.id
        elif not verify_entry(_sealed_fields(entry), previous_hash, key=AUDIT_KEY):
            return False, entry.id
        previous_hash = entry.entry_hash
    return True, None
