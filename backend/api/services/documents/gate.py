"""How many documents the process reads at once (§6: bounded work, fail fast).

The parsers, the PDF renderer and Tesseract all run in this process, in whichever
thread asked: an upload's request thread or an agent's run. A few heavy documents
at once would otherwise take every CPU and much of the memory from everyone else.
So each extraction holds a slot while it reads; one that cannot get a slot in time
is refused with DocumentReadersBusy, which tells the client when to try again.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from api.exceptions import DocumentReadersBusy

logger = logging.getLogger(__name__)

#: Process-wide slots, by how many there are. Settings give one number per server,
#: so in practice there is one semaphore; the lock makes sure of it.
_SLOTS: dict[int, threading.BoundedSemaphore] = {}
_SLOTS_LOCK = threading.Lock()


def _slots(count: int) -> threading.BoundedSemaphore:
    with _SLOTS_LOCK:
        if count not in _SLOTS:
            _SLOTS[count] = threading.BoundedSemaphore(count)
        return _SLOTS[count]


@contextmanager
def extraction_slot(count: int, wait_seconds: float) -> Iterator[None]:
    """Hold one of ``count`` process-wide slots while the block runs.

    Raises DocumentReadersBusy when none frees up within ``wait_seconds``.
    """
    slots = _slots(count)
    if not slots.acquire(timeout=wait_seconds):
        logger.warning("documents.busy slots=%d waited_s=%g", count, wait_seconds)
        raise DocumentReadersBusy(
            "The server is busy reading other documents. Try again in a moment.",
            retry_after=math.ceil(wait_seconds),
        )
    try:
        yield
    finally:
        slots.release()
