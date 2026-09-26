"""
File de travail PostgreSQL (procrastinate).

Un thread, une boucle asyncio à lui (selector : psycopg async refuse la
boucle Windows par défaut d'uvicorn), un worker qui prend les jobs en
SELECT ... FOR UPDATE SKIP LOCKED. Les jobs survivent à un redémarrage : un
job interrompu est remis en file au démarrage suivant. Un verrou par dépôt
sérialise les analyses d'un même projet, le reste tourne en parallèle.

Les routes déposent leurs jobs en confiant la coroutine à cette boucle
(run_coroutine_threadsafe) : une seule connexion ouverte, un seul endroit qui
parle à la file.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import sys
import threading
from collections.abc import Coroutine
from typing import Any

import procrastinate
from procrastinate import PsycopgConnector
from sqlalchemy import inspect

logger = logging.getLogger(__name__)

queue = procrastinate.App(connector=PsycopgConnector(), import_paths=["app.orchestration.jobs"])


class QueueWorker:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None

    @property
    def running(self) -> bool:
        return self._loop is not None and self._ready.is_set()

    def start(self, database_url: str, engine, concurrency: int) -> None:
        if self._thread is not None:
            return
        if "procrastinate_jobs" not in inspect(engine).get_table_names():
            # Première fois : les tables de la file. Les mises à jour de
            # procrastinate passent ensuite par `procrastinate schema --apply`.
            with queue.replace_connector(PsycopgConnector(conninfo=database_url)):
                queue.schema_manager.apply_schema()
            logger.info("Tables de la file de travail créées.")
        self._thread = threading.Thread(
            target=self._run, args=(database_url, concurrency), daemon=True, name="hadi-queue"
        )
        self._thread.start()
        if not self._ready.wait(timeout=30):
            raise RuntimeError("La file de travail n'a pas démarré.")

    def _run(self, database_url: str, concurrency: int) -> None:
        self._loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main(database_url, concurrency))
        except Exception as e:  # noqa: BLE001 : le thread ne doit pas mourir en silence
            logger.exception(f"File de travail arrêtée sur une erreur : {e}")
        finally:
            self._loop.close()

    async def _main(self, database_url: str, concurrency: int) -> None:
        self._stop = asyncio.Event()
        # replace_connector est un contexte : le connecteur reste en place tant
        # que le worker vit, c'est-à-dire toute la durée du process.
        with queue.replace_connector(PsycopgConnector(conninfo=database_url)):
            async with queue.open_async():
                await self._requeue_stalled()
                self._ready.set()
                worker = asyncio.create_task(
                    queue.run_worker_async(concurrency=concurrency, wait=True, install_signal_handlers=False)
                )
                await self._stop.wait()
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass

    async def _requeue_stalled(self) -> None:
        """Jobs laissés en cours par un process mort : remis en file, pas perdus."""
        stalled = list(await queue.job_manager.get_stalled_jobs())
        for job in stalled:
            await queue.job_manager.retry_job(job)
        if stalled:
            logger.warning(f"{len(stalled)} job(s) interrompu(s) par un redémarrage remis en file.")

    def submit(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        if self._loop is None or not self._ready.is_set():
            coro.close()
            raise RuntimeError("File de travail indisponible : la base n'est pas encore connectée.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self) -> None:
        if self._loop is None or self._stop is None:
            return
        self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=10)


worker = QueueWorker()
