"""Verification of Cognito access tokens against the user pool's public keys (JWKS)."""

import asyncio
from dataclasses import dataclass

import jwt

from app.core.config import Settings


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    groups: tuple[str, ...]


class TokenVerifier:
    def __init__(self, settings: Settings, jwks_client: jwt.PyJWKClient | None = None) -> None:
        self._issuer = settings.cognito_issuer
        self._client_id = settings.cognito_app_client_id
        # tests pass a client with their own key.
        self._jwks = jwks_client or jwt.PyJWKClient(settings.cognito_jwks_url)

    async def verify(self, token: str) -> TokenClaims:
        try:
            # may fetch the JWKS over HTTP (blocking)
            signing_key = await asyncio.to_thread(self._jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=30,
                options={"require": ["exp", "iat", "iss", "sub", "token_use", "client_id"]},
            )
        except jwt.PyJWKClientConnectionError:
            raise  # Cognito unreachable: a server error, not the caller's fault
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        if claims["token_use"] != "access":  # noqa: S105 - a claim value, not a password
            raise InvalidTokenError("not an access token")
        if claims["client_id"] != self._client_id:
            raise InvalidTokenError("issued to another app client")
        return TokenClaims(sub=claims["sub"], groups=tuple(claims.get("cognito:groups", [])))
