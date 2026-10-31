"""Image generation: a description in, one JPEG out (Muse Image).

Meta's ``/images/generations`` is OpenAI-compatible, so the call goes through the
Meta provider's client (``providers/meta.py``): same timeout, the retry policy of
llm/retry.py and the failure contract of llm/base.py (§5 L), so only
``ProviderTimeout`` or ``ProviderRequestError`` escape. JPEG, because a PNG of the
same picture is about four times larger (2.7 MB against 0.6 MB, measured).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Protocol

from llm.base import ProviderConfig, normalised_failures
from llm.exceptions import ProviderRequestError
from llm.providers import meta
from llm.retry import SYSTEM_CLOCK, Retrier, RetryClock

#: The provider whose key an image spends.
PROVIDER = meta.NAME
#: The shapes a caller may ask for, as the API's size hint (it sets the aspect ratio).
SIZES: dict[str, str] = {"square": "1024x1024", "landscape": "1792x1024", "portrait": "1024x1792"}


@dataclass(frozen=True)
class GeneratedImage:
    """One picture's JPEG bytes (§7 Value Object)."""

    jpeg: bytes


class ImageGenerator(Protocol):
    """Draws ``description`` in one of the ``SIZES`` shapes; fails as ``ProviderTimeout``
    or ``ProviderRequestError``."""

    def generate(self, description: str, shape: str) -> GeneratedImage: ...


class MetaImageGenerator:
    """Muse Image behind our own contract (§7 Adapter).

    ``config.default_model`` is the image model, e.g. ``muse-image-1.0``.
    """

    def __init__(self, config: ProviderConfig, clock: RetryClock = SYSTEM_CLOCK) -> None:
        self._client = meta.client(config)
        self._config = config
        self._clock = clock

    def generate(self, description: str, shape: str) -> GeneratedImage:
        model = self._config.default_model
        retrier = Retrier(self._config.retry, PROVIDER, model, self._clock)
        with normalised_failures(PROVIDER, model, self._config.timeout_seconds):
            answer = retrier.call(
                lambda: self._client.images.generate(
                    model=model,
                    prompt=description,
                    size=SIZES[shape],  # Meta reads it as an aspect ratio
                    n=1,
                    response_format="b64_json",
                    output_format="jpeg",
                )
            )
        return GeneratedImage(_decoded(answer))


def _decoded(answer: Any) -> bytes:
    data = getattr(answer, "data", None)
    encoded = getattr(data[0], "b64_json", None) if data else None
    if not encoded:
        raise ProviderRequestError(f"{PROVIDER} returned no image.")
    try:
        return base64.b64decode(encoded, validate=True)
    except binascii.Error as cause:
        raise ProviderRequestError(f"{PROVIDER} returned an unreadable image.") from cause
