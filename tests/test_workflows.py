import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(".github/workflows")
PIPELINE_DOCS = Path("docs/pipeline.md")
TERRAFORM = Path("infra/terraform")
AWS_CREDENTIALS_ACTION = "aws-actions/configure-aws-credentials"


def load(path: Path) -> dict[str, Any]:
    workflow: dict[Any, Any] = yaml.safe_load(path.read_text("utf-8"))
    # YAML 1.1 reads the key `on` as True
    if True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def all_workflows() -> dict[str, dict[str, Any]]:
    return {path.name: load(path) for path in sorted(WORKFLOWS.glob("*.yml"))}


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = job.get("steps", [])
    return result


def assumes_role(job: dict[str, Any]) -> bool:
    return any(step.get("uses", "").startswith(AWS_CREDENTIALS_ACTION) for step in steps(job))


@pytest.fixture(scope="module")
def ci() -> dict[str, Any]:
    return load(WORKFLOWS / "ci.yml")


def test_ci_runs_on_pull_requests_and_as_a_reusable_workflow(ci: dict[str, Any]) -> None:
    assert ci["on"]["pull_request"]["branches"] == ["main", "dev"]
    assert "workflow_call" in ci["on"]
    assert "push" not in ci["on"]


def test_ci_has_a_job_per_check(ci: dict[str, Any]) -> None:
    assert set(ci["jobs"]) == {
        "lint",
        "typecheck",
        "test",
        "evals",
        "frontend",
        "actionlint",
        "terraform",
    }


def test_the_test_job_runs_everything_with_coverage_of_at_least_80() -> None:
    ci = load(WORKFLOWS / "ci.yml")
    runs = [step.get("run", "") for step in steps(ci["jobs"]["test"])]
    assert "uv run pytest --cov --cov-report=term-missing" in runs
    pyproject = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))
    assert pyproject["tool"]["coverage"]["report"]["fail_under"] >= 80


def test_the_evals_run_as_their_own_job(ci: dict[str, Any]) -> None:
    runs = [step.get("run", "") for step in steps(ci["jobs"]["evals"])]
    assert "uv run pytest tests/evals --no-cov" in runs


def test_the_frontend_job_lints_and_type_checks(ci: dict[str, Any]) -> None:
    runs = [step.get("run", "") for step in steps(ci["jobs"]["frontend"])]
    assert "npm run lint" in runs
    assert "npm run typecheck" in runs


def test_every_terraform_root_is_validated(ci: dict[str, Any]) -> None:
    roots = ci["jobs"]["terraform"]["strategy"]["matrix"]["root"]
    assert roots == ["bootstrap", "environments/dev", "environments/prod"]
    for root in roots:
        assert (TERRAFORM / root / "main.tf").is_file()


@pytest.mark.parametrize("name", sorted(all_workflows()))
def test_aws_access_is_oidc_only(name: str) -> None:
    for job in all_workflows()[name]["jobs"].values():
        for step in steps(job):
            if step.get("uses", "").startswith(AWS_CREDENTIALS_ACTION):
                assert "role-to-assume" in step["with"]
                assert "aws-access-key-id" not in step["with"]
                assert "aws-secret-access-key" not in step["with"]
    text = (WORKFLOWS / name).read_text("utf-8")
    assert not re.search(r"secrets\.AWS|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY", text)


@pytest.mark.parametrize("name", sorted(all_workflows()))
def test_only_jobs_that_assume_a_role_get_an_oidc_token(name: str) -> None:
    workflow = all_workflows()[name]
    assert "id-token" not in workflow.get("permissions", {})
    for job_id, job in workflow["jobs"].items():
        wants_token = job.get("permissions", {}).get("id-token") == "write"
        assert wants_token == assumes_role(job), job_id


def test_every_job_and_named_step_is_documented() -> None:
    docs = PIPELINE_DOCS.read_text("utf-8")
    missing = [
        f"{name}: {item}"
        for name, workflow in all_workflows().items()
        for job_id, job in workflow["jobs"].items()
        for item in [job_id, *(step["name"] for step in steps(job) if "name" in step)]
        if f"`{item}`" not in docs
    ]
    assert missing == []
