"""Where pipeline runs execute: off the request path (AGENTS.md §6).

``BackgroundRunExecutor`` owns one asyncio event loop on a daemon thread,
started on first use and stopped by the app's lifespan. At most
``max_concurrent`` jobs execute at once; the others wait for a free slot. Jobs
are keyed by run id, so a request thread can cancel one, and can wait for the
last one under a key to have ended (``settled``): a stopped job may take a
while to wind down, and must not record its end over the next one's run.
``api/deps.run_executor`` hands the executor to the run service, so tests can
swap in one that runs jobs inline (Dependency Injection, §5 D).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import Future, wait
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RunExecutor(Protocol):
    """Executes run jobs. Every method is safe to call from any thread."""

    def submit(self, key: int, job: Callable[[], Awaitable[T]]) -> Future[T]:
        """Schedule ``job`` under ``key``; the future completes with its result,
        or is cancelled when the job is."""
        ...

    def cancel(self, key: int) -> None:
        """Cancel the job under ``key`` if it is waiting or executing; else do nothing."""
        ...

    def settled(self, key: int) -> bool:
        """Whether every job submitted under ``key`` has ended, after waiting a
        moment (the shutdown grace) for one that is still winding down."""
        ...

    def shutdown(self) -> None:
        """Cancel every job, give them a moment to wind down, and stop."""
        ...


class _Worker:
    """One event loop on a daemon thread, with its job slots and its live jobs."""

    def __init__(self, max_concurrent: int) -> None:
        self.loop = asyncio.new_event_loop()
        self.slots = asyncio.Semaphore(max_concurrent)
        #: Live jobs by key; only the loop's thread reads or writes it.
        self.jobs: dict[int, asyncio.Task[Any]] = {}
        self.thread = threading.Thread(target=self._serve, name="aimix-runs", daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    async def guarded(self, key: int, job: Callable[[], Awaitable[T]]) -> T:
        task = asyncio.current_task()
        assert task is not None  # always inside the loop's task
        self.jobs[key] = task
        try:
            async with self.slots:
                return await job()
        finally:
            if self.jobs.get(key) is task:
                del self.jobs[key]

    def cancel(self, key: int) -> None:
        job = self.jobs.get(key)
        if job is not None:
            job.cancel()

    async def cancel_all(self) -> int:
        jobs = list(self.jobs.values())
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        return len(jobs)


class BackgroundRunExecutor:
    """The app's executor: a bounded number of runs on a dedicated event loop."""

    def __init__(self, max_concurrent: int, grace_seconds: float) -> None:
        self._max_concurrent = max_concurrent
        self._grace_seconds = grace_seconds
        self._lock = threading.Lock()
        self._worker: _Worker | None = None
        #: The future of the last job submitted under each key, until that job ends.
        self._live: dict[int, Future[Any]] = {}

    def submit(self, key: int, job: Callable[[], Awaitable[T]]) -> Future[T]:
        worker = self._started()
        future = asyncio.run_coroutine_threadsafe(worker.guarded(key, job), worker.loop)
        with self._lock:
            self._live[key] = future
        # Done once the job's task has ended (nothing cancels this future itself).
        future.add_done_callback(lambda done: self._ended(key, done))
        return future

    def cancel(self, key: int) -> None:
        worker = self._worker
        if worker is not None:
            worker.loop.call_soon_threadsafe(worker.cancel, key)

    def settled(self, key: int) -> bool:
        with self._lock:
            live = self._live.get(key)
        if live is None:
            return True
        wait([live], timeout=self._grace_seconds)
        return live.done()

    def _ended(self, key: int, future: Future[Any]) -> None:
        with self._lock:
            if self._live.get(key) is future:
                del self._live[key]

    def shutdown(self) -> None:
        with self._lock:
            worker, self._worker = self._worker, None
            self._live.clear()
        if worker is None:
            return
        stopping = asyncio.run_coroutine_threadsafe(worker.cancel_all(), worker.loop)
        try:
            stopped = stopping.result(timeout=self._grace_seconds)
            logger.info("runs.executor_stopped cancelled_jobs=%d", stopped)
        except FutureTimeoutError:
            logger.warning("runs.executor_stop_timeout grace_s=%.1f", self._grace_seconds)
        worker.loop.call_soon_threadsafe(worker.loop.stop)
        worker.thread.join(timeout=self._grace_seconds)

    def _started(self) -> _Worker:
        """The running worker; the first job starts it, and one after a shutdown restarts it."""
        with self._lock:
            if self._worker is None:
                self._worker = _Worker(self._max_concurrent)
            return self._worker
