"""
Limiteur de débit partagé (slowapi). En mémoire par process : suffisant pour
la seule route publique de l'API (le webhook), et sans Redis à déployer.
Derrière un reverse-proxy, X-Forwarded-For est pris en compte par
get_remote_address si le proxy le renseigne.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
