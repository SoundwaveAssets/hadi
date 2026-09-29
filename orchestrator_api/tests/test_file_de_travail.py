"""
Dépôt de jobs : depuis quel thread, et ce qui est refusé. Sans PostgreSQL,
la boucle seule suffit à couvrir ces règles.
"""
import asyncio

import pytest

from app.orchestration.queue import QueueWorker


@pytest.fixture
def boucle():
    boucle = asyncio.new_event_loop()
    yield boucle
    boucle.close()


def test_sans_base_connectee_le_depot_est_refuse():
    async def rien():
        return None

    with pytest.raises(RuntimeError, match="pas encore connectée"):
        QueueWorker().submit(rien())


def test_deposer_depuis_la_boucle_de_la_file_est_refuse_au_lieu_d_interbloquer(boucle):
    """
    Attendre sur la boucle qui doit exécuter la coroutine ne se résout
    jamais : le dépôt expirait au bout du délai, l'appelant croyait la mise
    en file perdue et repartait par le chemin de secours, pendant que le job
    finissait par partir. Le travail était fait deux fois.
    """
    worker = QueueWorker()
    worker._loop = boucle
    worker._ready.set()

    async def depuis_la_boucle():
        async def rien():
            return None

        with pytest.raises(RuntimeError, match="variante asynchrone"):
            worker.submit(rien())

    boucle.run_until_complete(asyncio.wait_for(depuis_la_boucle(), timeout=5))


def test_depuis_un_autre_thread_le_depot_passe(boucle):
    worker = QueueWorker()
    worker._loop = boucle
    worker._ready.set()

    async def repondre():
        return 42

    future = worker.submit(repondre())
    boucle.run_until_complete(asyncio.sleep(0.05))
    assert future.result(timeout=5) == 42
