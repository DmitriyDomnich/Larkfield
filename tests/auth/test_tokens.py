import time
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.tokens import InvalidTokenError
from app.core.config import Settings
from tests.tokens import make_token, make_verifier


async def test_valid_access_token_gives_sub_and_groups(settings: Settings) -> None:
    token = make_token(settings, sub="abc", groups=["reviewer"])

    claims = await make_verifier(settings).verify(token)

    assert claims.sub == "abc"
    assert claims.groups == ("reviewer",)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"exp": int(time.time()) - 120}, id="expired"),
        pytest.param({"iss": "https://cognito-idp.eu-north-1.amazonaws.com/other"}, id="wrong-iss"),
        pytest.param({"token_use": "id"}, id="id-token"),
        pytest.param({"client_id": "another-client"}, id="wrong-client"),
        pytest.param({"sub": None}, id="missing-sub"),
        pytest.param({"kid": "unknown-key"}, id="unknown-kid"),
        pytest.param({"key": "x" * 32, "algorithm": "HS256"}, id="hs256"),
        pytest.param(
            {"key": rsa.generate_private_key(public_exponent=65537, key_size=2048)},
            id="bad-signature",
        ),
    ],
)
async def test_rejected_tokens(settings: Settings, overrides: dict[str, Any]) -> None:
    token = make_token(settings, **overrides)

    with pytest.raises(InvalidTokenError):
        await make_verifier(settings).verify(token)


def test_issuer_and_jwks_url_derive_from_settings(settings: Settings) -> None:
    settings.cognito_region = "eu-north-1"
    settings.cognito_user_pool_id = "eu-north-1_abc"

    assert settings.cognito_issuer == "https://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_abc"
    assert settings.cognito_jwks_url == f"{settings.cognito_issuer}/.well-known/jwks.json"
