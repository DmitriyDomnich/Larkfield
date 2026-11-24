from app.auth.cognito import DirectoryUser, UserDirectory
from app.auth.dependencies import CurrentUser
from app.auth.roles import ASSIGNABLE_ROLES, CLAIM_SUBMITTER_ROLES, Role


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


async def list_claim_submitters(directory: UserDirectory) -> list[DirectoryUser]:
    users = await directory.list_users_in_roles(CLAIM_SUBMITTER_ROLES)
    return sorted(users, key=lambda user: (user.email.lower(), user.sub))
