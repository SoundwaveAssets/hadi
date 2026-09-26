"""
Sondage d'un état distant jusqu'à une issue terminale (build Jenkins,
analyse SonarQube, synchronisation Argo CD). Une seule implémentation, sur
tenacity, plutôt qu'une boucle « échéance + sleep » réécrite dans chaque
client.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import AsyncRetrying, RetryError, retry_if_result, stop_after_delay, wait_fixed

T = TypeVar("T")


async def poll_until(probe: Callable[[], Awaitable[T | None]], *, timeout: float, interval: float) -> T | None:
    """
    Appelle `probe` toutes les `interval` secondes jusqu'à ce qu'elle renvoie
    autre chose que None, et renvoie cette valeur. None passé `timeout`
    secondes signifie « toujours pas d'issue ».

    Une exception levée par `probe` remonte immédiatement : c'est à l'appelant
    de décider si « injoignable » vaut échec ou simple attente.
    """
    try:
        return await AsyncRetrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
            retry=retry_if_result(lambda outcome: outcome is None),
            reraise=True,
        )(probe)
    except RetryError:
        return None
