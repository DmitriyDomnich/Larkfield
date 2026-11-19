"""The frontend's types are generated from frontend/openapi.json; it must match the API."""

from pathlib import Path

from app.openapi import openapi_document

SNAPSHOT = Path("frontend/openapi.json")


def test_committed_openapi_matches_the_api() -> None:
    assert SNAPSHOT.read_text("utf-8") == openapi_document(), (
        "The API changed: run `make openapi` and commit frontend/openapi.json"
    )
