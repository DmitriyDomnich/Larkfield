from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.cognito import UserDirectory, UserNotFoundError
from app.auth.dependencies import (
    CurrentUser,
    CurrentUserDep,
    get_user_directory,
    require_roles,
    unauthorized,
)
from app.auth.roles import Role
from app.auth.tokens import InvalidTokenError
from app.users.schemas import MeResponse, RoleResponse, RoleUpdate
from app.users.service import RoleNotAssignableError, SelfRoleChangeError, set_role

router = APIRouter(tags=["users"])

DirectoryDep = Annotated[UserDirectory, Depends(get_user_directory)]


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep, directory: DirectoryDep) -> MeResponse:
    try:
        email = await directory.get_email(user.access_token)
    except InvalidTokenError:
        raise unauthorized() from None
    return MeResponse(sub=user.sub, email=email, role=user.role)


@router.put("/users/{sub}/role", response_model=RoleResponse)
async def update_role(
    sub: str,
    body: RoleUpdate,
    admin: Annotated[CurrentUser, Depends(require_roles(Role.ADMIN))],
    directory: DirectoryDep,
) -> RoleResponse:
    try:
        await set_role(directory, admin, sub, body.role)
    except SelfRoleChangeError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot change your own role") from None
    except RoleNotAssignableError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Role {body.role} cannot be assigned"
        ) from None
    except UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    return RoleResponse(sub=sub, role=body.role)
