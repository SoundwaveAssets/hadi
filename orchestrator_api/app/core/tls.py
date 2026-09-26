"""
Vérification TLS des appels sortants.

httpx vérifie contre certifi, pas contre le magasin de l'OS : une autorité
locale (mkcert, CA d'entreprise) n'est jamais reconnue. `truststore` branche
la vérification sur le magasin du système, sans rien désactiver.

Reste le cas du certificat auto-signé sans autorité : celui d'Argo CD
déployé dans un cluster, c'est-à-dire l'immense majorité des installations.
Aucun magasin ne le reconnaîtra jamais. Deux issues honnêtes : importer son
certificat dans le magasin de l'OS, ou déclarer explicitement l'hôte comme
non vérifié (ORCHESTRATOR_TLS_SKIP_VERIFY_HOSTS). La seconde est un choix
d'exploitation, assumé hôte par hôte : jamais un défaut, jamais global.
"""
import ssl
from urllib.parse import urlsplit

import truststore

from app.config import get_settings

# Pas d'injection globale (truststore.inject_into_ssl) : elle vérifie toujours
# via le magasin de l'OS, même quand on demande explicitement de ne pas
# vérifier. Les contextes sont donc passés explicitement par les appelants.
# Les clients bâtis sur `requests` vérifient alors contre certifi :
# REQUESTS_CA_BUNDLE pour une autorité d'entreprise.
_UNVERIFIED = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_UNVERIFIED.check_hostname = False
_UNVERIFIED.verify_mode = ssl.CERT_NONE


def verify_context() -> ssl.SSLContext:
    """Vérification normale, adossée au magasin de certificats du système."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def skip_verify_hosts() -> frozenset[str]:
    """Hôtes déclarés non vérifiés, en minuscules, `host` ou `host:port`."""
    raw = get_settings().tls_skip_verify_hosts or ""
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def context_for(url: str) -> ssl.SSLContext:
    """
    Contexte TLS applicable à cette URL : vérification normale, sauf si
    l'exploitant a explicitement déclaré cet hôte comme non vérifié.
    """
    parts = urlsplit(url if "://" in url else f"https://{url}")
    hosts = skip_verify_hosts()
    candidats = {parts.netloc.lower(), (parts.hostname or "").lower()}
    return _UNVERIFIED if candidats & hosts else verify_context()
