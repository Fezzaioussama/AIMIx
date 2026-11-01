"""How many documents the process reads at once (§6: bounded work, fail fast).

The parsers, the PDF renderer and Tesseract all run in this process, in whichever
thread asked: an upload's request thread or an agent's run. A few heavy documents
at once would otherwise take every CPU and much of the memory from everyone else.
So each extraction holds a slot while it reads; one that cannot get a slot in time
is refused with DocumentReadersBusy, which tells the client when to try again.

Each ``SlotPool`` has slots of its own: an agent's OCR can hold one for minutes, and
must never keep a person's upload waiting; a link holds one of its pool from its
download to the end of its reading, so the bodies downloads buffer are bounded too.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from api.exceptions import DocumentReadersBusy
from api.services.documents.contracts import SlotPool

logger = logging.getLogger(__name__)

#: Process-wide slots, by pool and how many there are. Settings give one number per
#: pool and server, so in practice there is one semaphore per pool; the lock makes sure.
_SLOTS: dict[tuple[SlotPool, int], threading.BoundedSemaphore] = {}
_SLOTS_LOCK = threading.Lock()


def _slots(pool: SlotPool, count: int) -> threading.BoundedSemaphore:
    with _SLOTS_LOCK:
        if (pool, count) not in _SLOTS:
            _SLOTS[pool, count] = threading.BoundedSemaphore(count)
        return _SLOTS[pool, count]


@contextmanager
def extraction_slot(
    count: int, wait_seconds: float, pool: SlotPool = SlotPool.PEOPLE
) -> Iterator[None]:
    """Hold one of the ``count`` slots of ``pool`` while the block runs, waiting up to
    ``wait_seconds`` for one (0: refuse at once, which never blocks an event loop).

    Raises DocumentReadersBusy when none frees up within ``wait_seconds``.
    """
    slots = _slots(pool, count)
    if not slots.acquire(timeout=wait_seconds):
        logger.warning(
            "documents.busy pool=%s slots=%d waited_s=%g", pool.value, count, wait_seconds
        )
        raise DocumentReadersBusy(
            "The server is busy reading other documents. Try again in a moment.",
            retry_after=max(1, math.ceil(wait_seconds)),
        )
    try:
        yield
    finally:
        slots.release()
