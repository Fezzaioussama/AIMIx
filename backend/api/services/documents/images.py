"""Images, read by OCR: PNG, JPEG, WebP, TIFF (every page), BMP and GIF.

Pillow is fed untrusted files, so only the decoders in _DECODERS may run (never
EPS, PSD and the like), and a frame's pixel count, known from its header, is
checked against the limit before any of its pixels are decoded.
"""

from __future__ import annotations

from functools import partial
from io import BytesIO

from PIL import Image, ImageOps

from api.exceptions import DocumentUnreadable
from api.services.documents.contracts import ReadContext, ReadResult
from api.services.documents.scans import PageOcr

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif")
#: Any of these may decode any image upload, so a photo saved under the wrong
#: extension still reads. Nothing else Pillow knows is tried.
_DECODERS = ("PNG", "JPEG", "WEBP", "TIFF", "BMP", "GIF")
#: Formats whose frames are pages; the extra frames of the others are animation.
_PAGED = frozenset({"TIFF"})


def read_image(data: bytes, context: ReadContext) -> ReadResult:
    if context.ocr is None:
        raise DocumentUnreadable(
            "No text could be read from this image: images need OCR, which is not available."
        )
    max_pixels = context.limits.max_image_pixels
    image = _open(data, max_pixels)
    paged = image.format in _PAGED
    frames: int = getattr(image, "n_frames", 1) if paged else 1
    count = min(frames, context.limits.max_pages)
    scans = PageOcr(context)
    texts = [
        scans.read(index + 1, partial(_page, image, index, max_pixels)) for index in range(count)
    ]
    return ReadResult(
        "\n\n".join(texts),
        pages=frames if paged else None,
        cut_short=count < frames,
        omissions=scans.omissions(),
        ocr_pages=scans.pages_read,
    )


def _open(data: bytes, max_pixels: int) -> Image.Image:
    """The image with only its header read."""
    try:
        return Image.open(BytesIO(data), formats=_DECODERS)
    except Image.DecompressionBombError as cause:  # Pillow's own, far higher, limit
        raise _too_many_pixels(max_pixels) from cause


def _page(image: Image.Image, index: int, max_pixels: int) -> Image.Image:
    """Frame ``index`` as 8-bit gray on white and upright, once its size is known safe."""
    image.seek(index)
    if image.width * image.height > max_pixels:
        raise _too_many_pixels(max_pixels)
    page = _on_white(image)
    ImageOps.exif_transpose(page, in_place=True)  # phone photos are often stored sideways
    return page


def _on_white(image: Image.Image) -> Image.Image:
    """8-bit gray, with transparency flattened onto white so dark text stays readable."""
    if image.has_transparency_data:
        rgba = image.convert("RGBA")
        image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
    return image.convert("L")


def _too_many_pixels(max_pixels: int) -> DocumentUnreadable:
    return DocumentUnreadable(
        f"This image is too large to read: it has more than {max_pixels:,} pixels."
    )
