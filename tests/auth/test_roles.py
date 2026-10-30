import pytest

from app.auth.roles import Role, role_from_groups


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        (["employee"], Role.EMPLOYEE),
        (["employee", "admin", "reviewer"], Role.ADMIN),
        (["reviewer", "employee"], Role.REVIEWER),
        (["some-other-group", "reviewer"], Role.REVIEWER),
        (["some-other-group"], None),
        ([], None),
    ],
)
def test_most_privileged_known_group_wins(groups: list[str], expected: Role | None) -> None:
    assert role_from_groups(groups) == expected
