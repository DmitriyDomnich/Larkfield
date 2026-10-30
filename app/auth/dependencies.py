"""Who is calling, and may they? Use `CurrentUserDep` for any signed-in user and
`require_roles(...)` to restrict an endpoint:

    @router.get("/claims", dependencies=[Depends(require_roles(Role.REVIEWER))])
    async def list_claims(): ...

    @router.put("/users/{sub}/role")
    async def set_role(admin: Annotated[CurrentUser, Depends(require_roles(Role.ADMIN))]): ...
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.cognito import UserDirectory
from app.auth.roles import Role, role_from_groups
from app.auth.tokens import InvalidTokenError, TokenVerifier

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False)  # we answer 401 ourselves


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    role: Role
    access_token: str = field(repr=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def get_user_directory(request: Request) -> UserDirectory:
    directory: UserDirectory = request.app.state.user_directory
    return directory


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> CurrentUser:
    if credentials is None:
        raise unauthorized()
    try:
        claims = await verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        logger.info("Rejected access token: %s", exc)
        raise unauthorized() from None

    role = role_from_groups(claims.groups)
    if role is None:
        logger.warning("User %s has no role group", claims.sub)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No role assigned")
    return CurrentUser(sub=claims.sub, role=role, access_token=credentials.credentials)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Dependency that lets through only callers with one of `roles` (403 otherwise)."""
    allowed = frozenset(roles)

    async def check_role(user: CurrentUserDep) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return check_role
