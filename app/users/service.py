from app.auth.cognito import UserDirectory
from app.auth.dependencies import CurrentUser
from app.auth.roles import ASSIGNABLE_ROLES, Role


class SelfRoleChangeError(Exception):
    pass


class RoleNotAssignableError(Exception):
    pass


async def set_role(directory: UserDirectory, actor: CurrentUser, sub: str, role: Role) -> None:
    """Give user `sub` exactly `role`. Nobody changes their own role, admins included."""
    if sub == actor.sub:
        raise SelfRoleChangeError(sub)
    if role not in ASSIGNABLE_ROLES:
        raise RoleNotAssignableError(role)
    await directory.set_role(sub, role)
