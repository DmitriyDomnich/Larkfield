import hashlib

from app.core.hashing import file_sha256


async def test_file_sha256_is_the_hex_digest() -> None:
    assert await file_sha256(b"%PDF-1.7") == hashlib.sha256(b"%PDF-1.7").hexdigest()


async def test_different_bytes_give_different_hashes() -> None:
    assert await file_sha256(b"receipt A") != await file_sha256(b"receipt B")
