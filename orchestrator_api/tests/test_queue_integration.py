"""
File de travail contre un vrai PostgreSQL : thread, boucle dédiée, dépôt
d'un job depuis un autre thread, exécution, statut. Ne tourne que si
HADI_TEST_DATABASE_URL est défini (la base de la pile de test).
"""
import os
import time

import pytest
from sqlmodel import create_engine

from app.orchestration.queue import QueueWorker, queue

URL = os.getenv("HADI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="HADI_TEST_DATABASE_URL absent")

SEEN: list[int] = []


@queue.task(name="test.ping", queue="test")
async def ping(x: int) -> int:
    SEEN.append(x)
    return x * 2


def test_un_job_depose_depuis_une_route_est_execute():
    worker = QueueWorker()
    worker.start(URL, create_engine(URL), concurrency=1)
    try:
        job_id = worker.submit(ping.defer_async(x=21)).result(timeout=15)
        assert job_id
        deadline = time.time() + 20
        while 21 not in SEEN and time.time() < deadline:
            time.sleep(0.2)
        assert 21 in SEEN
        status = worker.submit(queue.job_manager.get_job_status_async(job_id)).result(timeout=15)
        assert status.value == "succeeded"
    finally:
        worker.stop()
