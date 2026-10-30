import pytest
from fastapi.testclient import TestClient

from app.auth.cognito import UserNotFoundError
from app.auth.dependencies import get_token_verifier, get_user_directory
from app.auth.roles import Role
from app.auth.tokens import InvalidTokenError
from app.core.config import Settings
from tests.tokens import make_token, make_verifier


class FakeUserDirectory:
    def __init__(self) -> None:
        self.roles: dict[str, Role] = {"admin-1": Role.ADMIN, "user-1": Role.EMPLOYEE}
        self.revoked = False

    async def get_email(self, access_token: str) -> str:
        if self.revoked:
            raise InvalidTokenError("token revoked")
        return "user@example.com"

    async def set_role(self, sub: str, role: Role) -> None:
        if sub not in self.roles:
            raise UserNotFoundError(sub)
        self.roles[sub] = role


@pytest.fixture
def directory(client: TestClient, settings: Settings) -> FakeUserDirectory:
    fake = FakeUserDirectory()
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_token_verifier] = lambda: make_verifier(settings)
    overrides[get_user_directory] = lambda: fake
    return fake


def bearer(
    settings: Settings, sub: str = "user-1", groups: tuple[str, ...] | list[str] = ("employee",)
) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(settings, sub=sub, groups=list(groups))}"}


def test_me_returns_identity_and_role(
    client: TestClient, directory: FakeUserDirectory, settings: Settings
) -> None:
    response = client.get("/me", headers=bearer(settings, groups=["reviewer"]))

    assert response.status_code == 200
    assert response.json() == {"sub": "user-1", "email": "user@example.com", "role": "reviewer"}


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-header"),
        pytest.param({"Authorization": "Basic dXNlcjpwYXNz"}, id="not-bearer"),
        pytest.param({"Authorization": "Bearer not-a-jwt"}, id="garbage"),
    ],
)
def test_me_without_valid_token_is_401(
    client: TestClient, directory: FakeUserDirectory, headers: dict[str, str]
) -> None:
    response = client.get("/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_revoked_token_is_401(
    client: TestClient, directory: FakeUserDirectory, settings: Settings
) -> None:
    directory.revoked = True

    assert client.get("/me", headers=bearer(settings)).status_code == 401


def test_user_without_role_group_is_403(
    client: TestClient, directory: FakeUserDirectory, settings: Settings
) -> None:
    response = client.get("/me", headers=bearer(settings, groups=[]))

    assert response.status_code == 403


def test_admin_makes_employee_a_reviewer(
    client: TestClient, directory: FakeUserDirectory, settings: Settings
) -> None:
    response = client.put(
        "/users/user-1/role",
        json={"role": "reviewer"},
        headers=bearer(settings, sub="admin-1", groups=["admin"]),
    )

    assert response.status_code == 200
    assert response.json() == {"sub": "user-1", "role": "reviewer"}
    assert directory.roles["user-1"] == Role.REVIEWER


@pytest.mark.parametrize(
    ("caller", "groups", "target", "role", "status"),
    [
        pytest.param("user-1", ["employee"], "admin-1", "reviewer", 403, id="employee"),
        pytest.param("user-1", ["reviewer"], "admin-1", "reviewer", 403, id="reviewer"),
        pytest.param("user-1", ["employee"], "user-1", "reviewer", 403, id="own-role-employee"),
        pytest.param("admin-1", ["admin"], "admin-1", "employee", 403, id="own-role-admin"),
        pytest.param("admin-1", ["admin"], "user-1", "admin", 422, id="grant-admin"),
        pytest.param("admin-1", ["admin"], "nobody", "reviewer", 404, id="unknown-user"),
    ],
)
def test_role_change_refused(
    client: TestClient,
    directory: FakeUserDirectory,
    settings: Settings,
    caller: str,
    groups: list[str],
    target: str,
    role: str,
    status: int,
) -> None:
    before = dict(directory.roles)

    response = client.put(
        f"/users/{target}/role", json={"role": role}, headers=bearer(settings, caller, groups)
    )

    assert response.status_code == status
    assert directory.roles == before
