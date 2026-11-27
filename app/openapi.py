import json
import sys
from pathlib import Path

from app.main import create_app


def openapi_document() -> str:
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    document = openapi_document()
    Path(sys.argv[1]).write_text(document, encoding="utf-8")
