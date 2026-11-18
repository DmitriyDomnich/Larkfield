import json

from app.main import create_app


def openapi_document() -> str:
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(openapi_document(), end="")
