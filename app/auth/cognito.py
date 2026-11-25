"""Calls to the Cognito user pool. boto3 is blocking, so every call runs in a worker thread."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import boto3

from app.auth.roles import Role
from app.auth.tokens import InvalidTokenError
from app.core.config import Settings

LIST_USERS_PAGE_SIZE = 60  # ListUsersInGroup returns per call


class UserNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class DirectoryUser:
    sub: str
    email: str


class UserDirectory(Protocol):
    async def get_email(self, access_token: str) -> str: ...

    async def set_role(self, sub: str, role: Role) -> None: ...

    async def list_users_in_roles(self, roles: Iterable[Role]) -> list[DirectoryUser]: ...


class CognitoUserDirectory:
    def __init__(self, settings: Settings) -> None:
        self._pool_id = settings.cognito_user_pool_id
        self._client = boto3.client("cognito-idp", region_name=settings.cognito_region)

    async def get_email(self, access_token: str) -> str:
        # GetUser is authorized by the user's own access token, not by AWS credentials.
        try:
            user = await asyncio.to_thread(self._client.get_user, AccessToken=access_token)
        except self._client.exceptions.NotAuthorizedException as exc:
            raise InvalidTokenError("token revoked") from exc  # e.g. after a global sign-out
        return next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "email")

    async def set_role(self, sub: str, role: Role) -> None:
        await asyncio.to_thread(self._set_role, sub, role)

    def _set_role(self, sub: str, role: Role) -> None:
        """Leave the user in exactly one role group. Admin APIs accept the sub as Username."""
        try:
            groups = self._client.admin_list_groups_for_user(UserPoolId=self._pool_id, Username=sub)
        except self._client.exceptions.UserNotFoundException as exc:
            raise UserNotFoundError(sub) from exc

        for group in groups["Groups"]:
            name = group.get("GroupName", "")
            if name in Role and name != role:
                self._client.admin_remove_user_from_group(
                    UserPoolId=self._pool_id, Username=sub, GroupName=name
                )
        self._client.admin_add_user_to_group(UserPoolId=self._pool_id, Username=sub, GroupName=role)

    async def list_users_in_roles(self, roles: Iterable[Role]) -> list[DirectoryUser]:
        return await asyncio.to_thread(self._list_users_in_roles, list(roles))

    def _list_users_in_roles(self, roles: list[Role]) -> list[DirectoryUser]:
        users: dict[str, DirectoryUser] = {}
        for role in roles:
            request: dict[str, Any] = {
                "UserPoolId": self._pool_id,
                "GroupName": role,
                "Limit": LIST_USERS_PAGE_SIZE,
            }
            while True:
                page = self._client.list_users_in_group(**request)
                for user in page["Users"]:
                    attributes = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
                    sub = attributes["sub"]
                    label = attributes.get("email") or user["Username"]
                    users[sub] = DirectoryUser(sub=sub, email=label)
                if not page.get("NextToken"):
                    break
                request["NextToken"] = page["NextToken"]
        return list(users.values())
