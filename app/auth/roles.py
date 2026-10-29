from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    """Values are the Cognito group names"""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    EMPLOYEE = "employee"


ASSIGNABLE_ROLES = frozenset({Role.EMPLOYEE, Role.REVIEWER})


def role_from_groups(groups: Iterable[str]) -> Role | None:
    """The most privileged role among the user's groups; None if none is a role."""
    names = set(groups)
    return next((role for role in Role if role in names), None)
