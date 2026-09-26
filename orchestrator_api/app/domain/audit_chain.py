"""
Chaînage d'intégrité du journal d'audit.

Différence avec l'implémentation précédente, et c'est toute la question : le
condensat est maintenant un **HMAC-SHA256 avec une clé**, pas un SHA-256 nu.

Un SHA-256 nu ne protège de rien face au modèle de menace que le journal
revendique (« altération via un accès direct à la base ») : la fonction est
publique et déterministe, donc qui peut écrire dans la table peut modifier une
ligne puis recalculer lui-même tous les condensats suivants. La chaîne se
reconstitue en une dizaine de lignes de Python.

Avec un HMAC, reconstituer la chaîne exige la clé. Elle doit donc vivre
ailleurs que dans la base qu'elle protège : variable d'environnement injectée
au déploiement, idéalement un coffre (Vault, KMS). Une clé rangée à côté des
données qu'elle authentifie ne protège de rien non plus.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class SealSchema:
    """
    Champs couverts par le condensat, par version. Ajouter un champ scellé =
    nouvelle version : les entrées déjà écrites gardent la leur et restent
    vérifiables ; tout champ hors de ces listes reste libre. Une chaîne = un
    schéma (décisions, actions d'administration), même clé, même algorithme.
    """

    versions: Mapping[int, Sequence[str]]

    @property
    def current(self) -> int:
        return max(self.versions)

    def fields(self, version: int) -> Sequence[str]:
        return self.versions[version]


_DECISION_V1 = (
    "timestamp",
    "developer_username",
    "repository_name",
    "commit_hash",
    "ai_anomaly_score",
    "ai_explanation",
    "sonarqube_vulnerabilities",
    "decision",
    "justification",
    "approved_by",
    "four_eyes_approved_by",
    "supersedes_audit_id",
)
#: Journal des décisions. v2 : provenance de l'identité du développeur
#: (domain/identity.py). v3 : critère de sécurité appliqué (domain/decision.py),
#: sans quoi une entrée ne dit pas sur quelle base elle a été rendue.
_DECISION_V2 = (*_DECISION_V1, "developer_identity_source")
DECISION_SEAL = SealSchema({1: _DECISION_V1, 2: _DECISION_V2, 3: (*_DECISION_V2, "security_criterion")})

#: Journal des actions d'administration (models/admin_event.py).
ADMIN_SEAL = SealSchema({1: ("timestamp", "actor", "actor_role", "action", "target_type", "target_id", "target_label", "before", "after", "ip")})

# Alias historiques du journal des décisions.
SEALED_FIELDS_BY_VERSION = DECISION_SEAL.versions
CURRENT_SEAL_VERSION = DECISION_SEAL.current
SEALED_FIELDS: Sequence[str] = DECISION_SEAL.fields(CURRENT_SEAL_VERSION)


def utc_isoformat(ts: datetime) -> str:
    """
    Représentation figée d'un horodatage : un datetime aware relu depuis la
    base peut revenir avec un autre offset pour le même instant, un naïf est
    UTC par convention. C'est cette chaîne, et elle seule, qui entre dans le sceau.
    """
    ts = ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def canonical_payload(entry: Mapping[str, Any], previous_hash: Optional[str], version: int | None = None, *, schema: SealSchema = DECISION_SEAL) -> bytes:
    """
    Représentation canonique et stable d'une entrée.

    `sort_keys` garantit un ordre indépendant de celui du dictionnaire source ;
    `default=str` normalise les types non sérialisables (datetime, Decimal).
    Le condensat précédent est préfixé plutôt qu'inclus comme champ, pour que
    le chaînage reste lisible et ne puisse pas être confondu avec une donnée
    métier portant le même nom. Le numéro de version n'entre pas dans les
    octets scellés : le modifier fait vérifier l'entrée avec la mauvaise liste
    de champs, donc échouer, ce qui suffit à le rendre inaltérable.
    """
    body = {field: entry.get(field) for field in schema.fields(version if version is not None else schema.current)}
    canonical = json.dumps(body, sort_keys=True, default=str, ensure_ascii=False, separators=(",", ":"))
    return f"{previous_hash or ''}\n{canonical}".encode()


def seal(entry: Mapping[str, Any], previous_hash: Optional[str], *, key: bytes, version: int | None = None, schema: SealSchema = DECISION_SEAL) -> str:
    """Condensat authentifié d'une entrée, chaîné à la précédente."""
    if not key:
        raise ValueError("Clé de scellement absente : le journal d'audit ne peut pas être scellé.")
    return hmac.new(key, canonical_payload(entry, previous_hash, version, schema=schema), hashlib.sha256).hexdigest()


def verify_entry(entry: Mapping[str, Any], previous_hash: Optional[str], *, key: bytes, schema: SealSchema = DECISION_SEAL) -> bool:
    """Comparaison à temps constant, ne jamais utiliser `==` sur un condensat. La version scellée est celle de l'entrée."""
    version = int(entry.get("seal_version") or schema.current)
    if version not in schema.versions:
        return False
    expected = seal(entry, previous_hash, key=key, version=version, schema=schema)
    return hmac.compare_digest(expected, str(entry.get("entry_hash") or ""))


def verify_chain(
    entries: Iterable[Mapping[str, Any]], *, key: bytes, schema: SealSchema = DECISION_SEAL
) -> tuple[bool, Optional[Any]]:
    """
    Rejoue la chaîne complète dans l'ordre d'insertion.

    Renvoie `(intègre, identifiant de la première entrée en défaut)`. La
    première rupture arrête la vérification : au-delà, tous les condensats
    seraient faux par construction (chaînage), ce qui noierait le point de
    rupture réel dans du bruit.
    """
    previous_hash: Optional[str] = None
    for entry in entries:
        if not verify_entry(entry, previous_hash, key=key, schema=schema):
            return False, entry.get("id")
        previous_hash = str(entry.get("entry_hash"))
    return True, None
