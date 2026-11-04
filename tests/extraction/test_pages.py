import io

import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from app.extraction.pages import MAX_EDGE_PX, UnusableFileError, document_to_images
from tests.extraction.fakes import document_bytes


def pdf(pages: int) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    for number in range(pages):
        canvas.drawString(72, 720, f"Page {number + 1}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def jpeg(width: int, height: int, orientation: int | None = None) -> bytes:
    buffer = io.BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def test_every_pdf_page_becomes_a_png_at_the_model_resolution() -> None:
    pages = document_to_images(pdf(3), "application/pdf", max_pages=10)

    assert [page.format for page in pages] == ["png"] * 3
    assert all(max(size(page.data)) == MAX_EDGE_PX for page in pages)


def test_a_generated_receipt_renders() -> None:
    (page,) = document_to_images(document_bytes("D16.pdf"), "application/pdf", max_pages=10)

    assert max(size(page.data)) == MAX_EDGE_PX


def test_pdf_over_the_page_limit_is_refused() -> None:
    with pytest.raises(UnusableFileError) as refused:
        document_to_images(pdf(3), "application/pdf", max_pages=2)

    assert refused.value.reason == "The PDF has 3 pages; at most 2 can be processed"


def test_pdf_that_does_not_open_is_refused() -> None:
    with pytest.raises(UnusableFileError, match="The PDF could not be opened"):
        document_to_images(
            b"%PDF-1.7 and then nothing a PDF needs", "application/pdf", max_pages=10
        )


def test_large_photo_is_shrunk_to_a_jpeg() -> None:
    (page,) = document_to_images(jpeg(4000, 3000), "image/jpeg", max_pages=10)

    assert page.format == "jpeg"
    assert size(page.data) == (MAX_EDGE_PX, 1176)


def test_photo_is_turned_upright_from_its_exif_rotation() -> None:
    # orientation 6: the camera was held sideways, the pixels are stored landscape
    (page,) = document_to_images(jpeg(800, 600, orientation=6), "image/jpeg", max_pages=10)

    assert size(page.data) == (600, 800)


def test_png_photo_is_sent_as_jpeg() -> None:
    buffer = io.BytesIO()
    Image.new("RGBA", (300, 200)).save(buffer, format="PNG")

    (page,) = document_to_images(buffer.getvalue(), "image/png", max_pages=10)

    assert page.format == "jpeg"
    assert size(page.data) == (300, 200)


def test_image_that_does_not_open_is_refused() -> None:
    with pytest.raises(UnusableFileError, match="The image could not be opened"):
        document_to_images(b"\xff\xd8\xff not really a jpeg", "image/jpeg", max_pages=10)
