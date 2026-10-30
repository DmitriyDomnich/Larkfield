"""Cognito-like access tokens signed with a key generated here, so tests never call Cognito."""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.tokens import TokenVerifier
from app.core.config import Settings

KID = "test-key"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StaticJWKClient(jwt.PyJWKClient):
    """Serves our public key as the pool's JWKS instead of fetching it."""

    def __init__(self) -> None:
        super().__init__("https://jwks.invalid")
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(PRIVATE_KEY.public_key(), as_dict=True)
        self._jwks = {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}

    def fetch_data(self) -> Any:
        return self._jwks


def make_verifier(settings: Settings) -> TokenVerifier:
    return TokenVerifier(settings, jwks_client=StaticJWKClient())


def make_token(
    settings: Settings,
    key: Any = PRIVATE_KEY,
    algorithm: str = "RS256",
    kid: str = KID,
    **claims: Any,
) -> str:
    """A valid access token for an employee; override a claim with `name=value`, drop it with
    `name=None`. `cognito:groups` is passed as `groups`."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user-1",
        "iss": settings.cognito_issuer,
        "client_id": settings.cognito_app_client_id,
        "token_use": "access",
        "iat": now,
        "exp": now + 900,
        "cognito:groups": claims.pop("groups", ["employee"]),
    }
    payload.update(claims)
    payload = {name: value for name, value in payload.items() if value is not None}
    return jwt.encode(payload, key, algorithm=algorithm, headers={"kid": kid})
