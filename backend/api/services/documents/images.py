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
#: 16-bit gray, as some scanners save: values 0-65535.
_WIDE_GRAY = frozenset({"I;16", "I;16L", "I;16B", "I;16N"})


def read_image(data: bytes, context: ReadContext) -> ReadResult:
    if context.ocr is None:
        raise DocumentUnreadable(
            "No text could be read from this image: images need OCR, which is not available."
        )
    max_pixels = context.limits.max_image_pixels
    scans = PageOcr(context)
    with _open(data, max_pixels) as image:
        paged = image.format in _PAGED
        count, more = _count_pages(image, context.limits.max_pages) if paged else (1, False)
        texts = [
            scans.read(index + 1, partial(_page, image, index, max_pixels))
            for index in range(count)
        ]
    return ReadResult(
        "\n\n".join(texts),
        pages=count if paged else None,
        cut_short=more,
        omissions=scans.omissions(),
        ocr_pages=scans.pages_read,
    )


def _count_pages(image: Image.Image, limit: int) -> tuple[int, bool]:
    """The pages to read (at most ``limit``), and whether more follow.

    Counted by seeking, never with ``n_frames``: to count, Pillow walks every page of
    a TIFF in time that grows with the square of their number, and a 10 MB file
    can hold tens of thousands of tiny pages.
    """
    for index in range(1, limit + 1):
        try:
            image.seek(index)
        except EOFError:
            return index, False
    return limit, True


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
    # Photos are often stored sideways, with an EXIF rotation. The gray copy has no
    # EXIF of its own (a TIFF keeps it in its tags), so it is given the original's.
    page.info["exif"] = image.getexif().tobytes()
    ImageOps.exif_transpose(page, in_place=True)
    return page


def _on_white(image: Image.Image) -> Image.Image:
    """8-bit gray, with transparency flattened onto white so dark text stays readable."""
    if image.mode in _WIDE_GRAY:  # convert() would clip these to 8 bits, not scale them
        return image.convert("I").point(lambda value: value / 256).convert("L")
    if image.has_transparency_data:
        rgba = image.convert("RGBA")
        image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
    return image.convert("L")


def _too_many_pixels(max_pixels: int) -> DocumentUnreadable:
    return DocumentUnreadable(
        f"This image is too large to read: it has more than {max_pixels:,} pixels."
    )
