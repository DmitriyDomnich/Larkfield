from collections.abc import Iterator

import pytest
from botocore.stub import Stubber

from app.auth.cognito import CognitoUserDirectory, DirectoryUser, UserNotFoundError
from app.auth.roles import Role
from app.core.config import Settings


@pytest.fixture
def directory(settings: Settings) -> CognitoUserDirectory:
    return CognitoUserDirectory(settings)


@pytest.fixture
def stub(directory: CognitoUserDirectory) -> Iterator[Stubber]:
    """Answers boto3 calls from a script instead of AWS, and checks the parameters sent."""
    with Stubber(directory._client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


async def test_set_role_leaves_user_in_exactly_that_role(
    directory: CognitoUserDirectory, stub: Stubber, settings: Settings
) -> None:
    user = {"UserPoolId": settings.cognito_user_pool_id, "Username": "user-1"}
    groups = [{"GroupName": "employee"}, {"GroupName": "beta-testers"}]
    stub.add_response("admin_list_groups_for_user", {"Groups": groups}, user)
    stub.add_response("admin_remove_user_from_group", {}, {**user, "GroupName": "employee"})
    stub.add_response("admin_add_user_to_group", {}, {**user, "GroupName": "reviewer"})

    await directory.set_role("user-1", Role.REVIEWER)


async def test_set_role_of_unknown_user(directory: CognitoUserDirectory, stub: Stubber) -> None:
    stub.add_client_error("admin_list_groups_for_user", service_error_code="UserNotFoundException")

    with pytest.raises(UserNotFoundError):
        await directory.set_role("nobody", Role.REVIEWER)


def cognito_user(sub: str, email: str) -> dict[str, object]:
    return {
        "Username": sub,
        "Attributes": [{"Name": "sub", "Value": sub}, {"Name": "email", "Value": email}],
    }


async def test_list_users_reads_every_page_of_every_group(
    directory: CognitoUserDirectory, stub: Stubber, settings: Settings
) -> None:
    pool = settings.cognito_user_pool_id
    employees = {"UserPoolId": pool, "GroupName": "employee", "Limit": 60}
    reviewers = {"UserPoolId": pool, "GroupName": "reviewer", "Limit": 60}
    stub.add_response(
        "list_users_in_group",
        {"Users": [cognito_user("a", "a@example.com")], "NextToken": "page-2"},
        employees,
    )
    stub.add_response(
        "list_users_in_group",
        {"Users": [cognito_user("b", "b@example.com")]},
        {**employees, "NextToken": "page-2"},
    )
    stub.add_response(
        "list_users_in_group",
        {"Users": [cognito_user("r", "r@example.com"), cognito_user("b", "b@example.com")]},
        reviewers,
    )

    users = await directory.list_users_in_roles([Role.EMPLOYEE, Role.REVIEWER])

    assert sorted(users, key=lambda user: user.sub) == [
        DirectoryUser("a", "a@example.com"),
        DirectoryUser("b", "b@example.com"),
        DirectoryUser("r", "r@example.com"),
    ]
