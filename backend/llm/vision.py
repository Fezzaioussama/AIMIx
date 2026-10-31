"""Finding objects: a picture and a short noun phrase in, a box per match out (SAM 3.1).

Meta serves SAM 3.1 on its Responses endpoint: one user message with an
``input_text`` (what to find, e.g. "loaf of bread") and an ``input_image`` (a data
URL). The answer is one line of text holding a box and a mask per match,
``<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..;c=..|><|mask;...|>``; only the boxes are
read. The call goes through the Meta provider's client: same timeout, retry policy
and failure contract (§5 L) as chat, speech and images.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Protocol, cast

from llm.base import ProviderConfig, normalised_failures
from llm.exceptions import ProviderRequestError
from llm.providers import meta
from llm.retry import SYSTEM_CLOCK, Retrier, RetryClock

#: The provider whose key a search spends.
PROVIDER = meta.NAME
#: Confidence on each box; the one-bit masks keep the answer small (they are not read).
OPTIONS = {"include_confidence": "true", "mask_encoding": "one_bit"}
_BOX = re.compile(r"<\|box;([^|]*)\|>")


@dataclass(frozen=True)
class Box:
    """One match, in pixels of the picture; ``x2`` and ``y2`` are inclusive."""

    x1: int
    y1: int
    x2: int
    y2: int
    #: How sure the model is, from 0 to 1.
    confidence: float


@dataclass(frozen=True)
class Detection:
    """Every match of one search (§7 Value Object); no boxes when nothing matched."""

    boxes: tuple[Box, ...]


class ObjectFinder(Protocol):
    """Finds every ``what`` in a PNG or JPEG; fails as ``ProviderTimeout`` or
    ``ProviderRequestError``."""

    def find(self, image: bytes, media_type: str, what: str) -> Detection: ...


class MetaObjectFinder:
    """SAM 3.1 behind our own contract (§7 Adapter).

    ``config.default_model`` is the vision model, e.g. ``sam-3.1``.
    """

    def __init__(self, config: ProviderConfig, clock: RetryClock = SYSTEM_CLOCK) -> None:
        self._client = meta.client(config)
        self._config = config
        self._clock = clock

    def find(self, image: bytes, media_type: str, what: str) -> Detection:
        model = self._config.default_model
        picture = f"data:{media_type};base64,{base64.b64encode(image).decode()}"
        message = {
            "role": "user",
            "content": [
                {"type": "input_text", "text": what},
                {"type": "input_image", "image_url": picture},
            ],
        }
        retrier = Retrier(self._config.retry, PROVIDER, model, self._clock)
        with normalised_failures(PROVIDER, model, self._config.timeout_seconds):
            answer = retrier.call(
                # The SDK types the input for OpenAI's own fields; Meta's is a subset.
                lambda: self._client.responses.create(
                    model=model, input=cast(Any, [message]), metadata=OPTIONS
                )
            )
        return _detection(getattr(answer, "output_text", ""))


def _detection(text: str) -> Detection:
    return Detection(tuple(_box(fields) for fields in _BOX.findall(text or "")))


def _box(fields: str) -> Box:
    values = dict(part.split("=", 1) for part in fields.split(";") if "=" in part)
    try:
        corners = (int(values["x1"]), int(values["y1"]), int(values["x2"]), int(values["y2"]))
        return Box(*corners, confidence=float(values.get("c", "1")))
    except (KeyError, ValueError) as cause:
        raise ProviderRequestError(f"{PROVIDER} returned a box it did not describe.") from cause
