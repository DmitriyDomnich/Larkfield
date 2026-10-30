import pytest

from app.claims.files import content_disposition, content_matches_type
from tests.claims.fakes import EXE, PDF

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00"


@pytest.mark.parametrize(
    ("first_bytes", "content_type", "expected"),
    [
        pytest.param(PDF, "application/pdf", True, id="pdf"),
        pytest.param(JPEG, "image/jpeg", True, id="jpeg"),
        pytest.param(PNG, "image/png", True, id="png"),
        pytest.param(EXE, "application/pdf", False, id="windows-executable-as-pdf"),
        pytest.param(b"\x7fELF\x02\x01\x01", "application/pdf", False, id="linux-executable"),
        pytest.param(b"PK\x03\x04\x14\x00", "application/pdf", False, id="zip-as-pdf"),
        pytest.param(b"Total: 18.50 EUR", "image/jpeg", False, id="text-as-jpeg"),
        pytest.param(PNG, "application/pdf", False, id="png-as-pdf"),
        pytest.param(JPEG, "image/png", False, id="jpeg-as-png"),
        pytest.param(b"", "image/png", False, id="empty"),
    ],
)
def test_content_matches_type(first_bytes: bytes, content_type: str, expected: bool) -> None:
    assert content_matches_type(first_bytes, content_type) is expected


def test_content_disposition_keeps_unsafe_characters_out_of_the_plain_filename() -> None:
    header = content_disposition('Käse "x"\r\nSet-Cookie: a.pdf')

    assert header.startswith("inline; filename=\"K_se _x___Set-Cookie_ a.pdf\"; filename*=UTF-8''")
    assert "\r" not in header and "\n" not in header
    assert header.endswith("K%C3%A4se%20%22x%22%0D%0ASet-Cookie%3A%20a.pdf")
