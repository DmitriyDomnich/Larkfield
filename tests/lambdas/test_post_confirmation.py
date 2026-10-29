from typing import Any
from unittest.mock import MagicMock

import pytest

from lambdas.post_confirmation import handler as post_confirmation


@pytest.fixture
def cognito(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(post_confirmation, "cognito", fake)
    monkeypatch.setenv("DEFAULT_GROUP", "employee")
    return fake


def event(trigger_source: str) -> dict[str, Any]:
    return {"triggerSource": trigger_source, "userPoolId": "pool-1", "userName": "user-1"}


def test_new_user_joins_employee_group(cognito: MagicMock) -> None:
    signup = event("PostConfirmation_ConfirmSignUp")

    assert post_confirmation.handler(signup, None) == signup
    cognito.admin_add_user_to_group.assert_called_once_with(
        UserPoolId="pool-1", Username="user-1", GroupName="employee"
    )


def test_password_reset_changes_no_groups(cognito: MagicMock) -> None:
    post_confirmation.handler(event("PostConfirmation_ConfirmForgotPassword"), None)

    cognito.admin_add_user_to_group.assert_not_called()
