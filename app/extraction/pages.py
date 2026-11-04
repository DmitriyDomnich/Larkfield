import io
from dataclasses import dataclass
from typing import Literal

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_EDGE_PX = 1568


@dataclass(frozen=True)
class PageImage:
    data: bytes
    format: Literal["png", "jpeg"]


class UnusableFileError(Exception):
    """`reason` is for the employee."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def document_to_images(data: bytes, content_type: str, max_pages: int) -> list[PageImage]:
    if content_type == "application/pdf":
        return _render_pdf_pages(data, max_pages)
    return [_prepare_photo(data)]


def _render_pdf_pages(data: bytes, max_pages: int) -> list[PageImage]:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        raise UnusableFileError("The PDF could not be opened") from None
    try:
        if len(pdf) == 0:
            raise UnusableFileError("The PDF has no pages")
        if len(pdf) > max_pages:
            raise UnusableFileError(
                f"The PDF has {len(pdf)} pages; at most {max_pages} can be processed"
            )
        pages = []
        for page in pdf:
            width, height = page.get_size()
            scale = MAX_EDGE_PX / max(width, height)
            image = page.render(scale=scale).to_pil()
            pages.append(PageImage(_encode_image(image, "PNG"), "png"))
        return pages
    finally:
        pdf.close()


def _prepare_photo(data: bytes) -> PageImage:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise UnusableFileError("The image could not be opened") from None
    image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
    return PageImage(_encode_image(image, "JPEG"), "jpeg")


def _encode_image(image: Image.Image, image_format: Literal["PNG", "JPEG"]) -> bytes:
    buffer = io.BytesIO()
    if image_format == "JPEG":
        image.save(buffer, format="JPEG", quality=85)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
