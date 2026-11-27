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


ENVIRONMENT_PER_BRANCH = "github.ref_name == 'main' && 'prod' || 'dev'"
RUNTIME_ONLY = "steps.vars.outputs.runtime_enabled == 'true'"


@pytest.fixture(scope="module")
def deploy() -> dict[str, Any]:
    return load(WORKFLOWS / "deploy.yml")


@pytest.fixture(scope="module")
def switch() -> dict[str, Any]:
    job: dict[str, Any] = load(WORKFLOWS / "environment.yml")["jobs"]["switch"]
    return job


def named_steps(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["name"]: step for step in steps(job) if "name" in step}


def test_a_push_to_dev_or_main_deploys(deploy: dict[str, Any]) -> None:
    assert deploy["on"]["push"]["branches"] == ["dev", "main"]
    assert "workflow_dispatch" in deploy["on"]


def test_the_deploy_runs_ci_first_on_a_push(deploy: dict[str, Any]) -> None:
    assert deploy["jobs"]["ci"]["uses"] == "./.github/workflows/ci.yml"
    assert deploy["jobs"]["ci"]["if"] == "github.event_name == 'push'"
    job = deploy["jobs"]["deploy"]
    assert job["needs"] == "ci"
    assert "needs.ci.result == 'success'" in job["if"]


def test_main_deploys_prod_and_dev_deploys_dev(deploy: dict[str, Any]) -> None:
    job = deploy["jobs"]["deploy"]
    assert ENVIRONMENT_PER_BRANCH in job["environment"]
    assert ENVIRONMENT_PER_BRANCH in job["env"]["ENVIRONMENT"]
    assert deploy["concurrency"]["cancel-in-progress"] is False


def test_the_deploy_steps_run_in_order(deploy: dict[str, Any]) -> None:
    order = [
        "mask the email addresses",
        "assume the deploy role",
        "image to ECR",
        "build the clause files",
        "terraform variables",
        "terraform init",
        "record the live release",
        "terraform apply",
        "sync the policy knowledge base",
        "run the migration",
        "deploy the API and workers",
        "release the frontend",
        "smoke request",
        "roll back the AgentCore runtime",
        "roll back",
    ]
    names = list(named_steps(deploy["jobs"]["deploy"]))
    assert [name for name in names if name in order] == order


def test_a_stopped_environment_gets_infrastructure_and_image_only(deploy: dict[str, Any]) -> None:
    job_steps = named_steps(deploy["jobs"]["deploy"])
    for name in ["image to ECR", "record the live release", "terraform apply"]:
        assert "if" not in job_steps[name]
    for name in ["run the migration", "deploy the API and workers", "release the frontend"]:
        assert job_steps[name]["if"] == RUNTIME_ONLY
    assert job_steps["smoke request"]["if"] == RUNTIME_ONLY
    assert "runtime_enabled != 'true'" in job_steps["note a stopped environment"]["if"]


def test_any_failure_after_the_migration_rolls_back(deploy: dict[str, Any]) -> None:
    job_steps = named_steps(deploy["jobs"]["deploy"])
    assert job_steps["run the migration"]["id"] == "migrate"
    assert job_steps["roll back"]["if"] == "failure() && steps.migrate.outcome == 'success'"
    assert "previous-revisions.txt" in job_steps["record the live release"]["run"]
    assert "previous-revisions.txt" in job_steps["roll back"]["run"]
    assert "PREVIOUS_RELEASE" in job_steps["roll back"]["run"]


def test_the_migration_must_exit_0_and_the_new_revision_must_stick(deploy: dict[str, Any]) -> None:
    job_steps = named_steps(deploy["jobs"]["deploy"])
    assert '[ "$exit_code" = "0" ]' in job_steps["run the migration"]["run"]
    assert "deployments[?status=='PRIMARY']" in job_steps["deploy the API and workers"]["run"]


def test_the_smoke_request_goes_through_cloudfront(deploy: dict[str, Any]) -> None:
    run = named_steps(deploy["jobs"]["deploy"])["smoke request"]["run"]
    assert '"${SITE_URL}/api/health"' in run
    assert '.database == "ok"' in run
    assert '"${SITE_URL}/"' in run


def test_start_and_stop_are_dispatched_per_branch_in_their_own_queue(
    switch: dict[str, Any], deploy: dict[str, Any]
) -> None:
    workflow = load(WORKFLOWS / "environment.yml")
    assert workflow["on"]["workflow_dispatch"]["inputs"]["action"]["options"] == ["start", "stop"]
    assert ENVIRONMENT_PER_BRANCH in switch["environment"]
    # one pending run per group: in the deploy's queue a push would cancel a waiting Stop
    assert workflow["concurrency"]["group"] != deploy["concurrency"]["group"]


def test_start_and_stop_write_the_flag_and_run_the_deploy(switch: dict[str, Any]) -> None:
    job_steps = named_steps(switch)
    assert (
        "/larkfield-${ENVIRONMENT}/runtime_enabled" in job_steps["switch the runtime flag"]["run"]
    )
    assert "gh workflow run deploy.yml" in job_steps["run the deploy"]["run"]
    assert switch["permissions"]["actions"] == "write"


def test_stop_drops_the_old_snapshot_only_while_the_database_exists(switch: dict[str, Any]) -> None:
    drop = named_steps(switch)["drop the previous snapshot"]
    assert drop["if"] == "inputs.action == 'stop'"
    run = drop["run"]
    assert run.index("describe-db-instances") < run.index("delete-db-snapshot")


def test_services_get_tasks_only_from_the_deploy_after_the_migration(
    deploy: dict[str, Any],
) -> None:
    run = named_steps(deploy["jobs"]["deploy"])["deploy the API and workers"]["run"]
    assert "--desired-count 1" in run
    runtime = (TERRAFORM / "modules/runtime/main.tf").read_text("utf-8")
    assert re.search(r"desired_count\s+= 0", runtime)
    assert "ignore_changes = [task_definition, desired_count]" in runtime


def test_replaced_task_definitions_stay_active_for_the_rollback() -> None:
    runtime = (TERRAFORM / "modules/runtime/main.tf").read_text("utf-8")
    assert re.search(r"skip_destroy\s+= true", runtime)


def test_the_frontend_release_and_its_rollback_publish_the_same_way(deploy: dict[str, Any]) -> None:
    job_steps = named_steps(deploy["jobs"]["deploy"])
    for name in ["release the frontend", "roll back"]:
        assert "infra/scripts/publish-release.sh" in job_steps[name]["run"]


def test_the_email_addresses_are_masked_before_anything_is_logged(deploy: dict[str, Any]) -> None:
    first = steps(deploy["jobs"]["deploy"])[0]
    assert first["name"] == "mask the email addresses"
    assert first["env"]["TFVARS"] == "${{ vars.TFVARS }}"
    assert "::add-mask::" in first["run"]


def test_the_agent_runtime_is_v1_public_with_a_one_minute_idle_timeout() -> None:
    runtime = (TERRAFORM / "modules/agent_runtime/main.tf").read_text("utf-8")
    assert re.search(r'platform_version\s+= "V1"', runtime)
    assert re.search(r'network_mode\s+= "PUBLIC"', runtime)
    assert re.search(r"idle_runtime_session_timeout\s+= 60\b", runtime)
    assert '"${var.repository_url}:${var.image_tag}-agent-runtime"' in runtime
    assert "authorizer_configuration" not in runtime  # SigV4, the default


def test_the_agent_runtime_role_reaches_only_the_model_the_kb_and_its_logs() -> None:
    runtime = (TERRAFORM / "modules/agent_runtime/main.tf").read_text("utf-8")
    assert '"bedrock-agentcore.amazonaws.com"' in runtime
    assert '"aws:SourceAccount"' in runtime
    assert '"aws:SourceArn"' in runtime
    for forbidden in ["sqs:", "secretsmanager:", "rds:", "s3:"]:
        assert forbidden not in runtime
    assert '"logs:CreateLogGroup"' not in runtime  # terraform creates the group with its retention


def test_the_review_worker_invokes_the_runtime_instead_of_bedrock() -> None:
    review = (TERRAFORM / "modules/review/main.tf").read_text("utf-8")
    assert '"bedrock-agentcore:InvokeAgentRuntime"' in review
    assert '"${var.agent_runtime_arn}/runtime-endpoint/*"' in review
    assert "bedrock:InvokeModel" not in review
    assert "bedrock:Retrieve" not in review


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_each_environment_points_the_review_worker_at_its_runtime(environment: str) -> None:
    root = (TERRAFORM / "environments" / environment / "main.tf").read_text("utf-8")
    assert re.search(r"REVIEW_AGENT_RUNTIME_ARN\s+= module\.agent_runtime\.runtime_arn", root)
    assert re.search(r"agent_runtime_arn\s+= module\.agent_runtime\.runtime_arn", root)


def test_the_tasks_run_on_arm64_like_the_runtime() -> None:
    runtime = (TERRAFORM / "modules/runtime/main.tf").read_text("utf-8")
    assert re.search(r'cpu_architecture\s+= "ARM64"', runtime)
    assert "X86_64" not in runtime


def test_the_deploy_builds_natively_on_arm64(deploy: dict[str, Any]) -> None:
    assert deploy["jobs"]["deploy"]["runs-on"] == "ubuntu-24.04-arm"
    push = Path("infra/scripts/push-image.sh").read_text("utf-8")
    assert 'push_target app "${IMAGE_TAG:?}"' in push
    assert 'push_target agent-runtime "${IMAGE_TAG}-agent-runtime"' in push


def test_the_live_runtime_configuration_is_recorded_before_the_apply(
    deploy: dict[str, Any],
) -> None:
    run = named_steps(deploy["jobs"]["deploy"])["record the live release"]["run"]
    assert "previous .agent_runtime.value.id" in run
    assert "get-agent-runtime" in run
    assert "previous-agent-runtime.json" in run
    for environment in ["dev", "prod"]:
        outputs = (TERRAFORM / "environments" / environment / "outputs.tf").read_text("utf-8")
        assert 'output "agent_runtime"' in outputs


def test_any_failure_after_the_apply_rolls_the_runtime_back(deploy: dict[str, Any]) -> None:
    job_steps = named_steps(deploy["jobs"]["deploy"])
    rollback = job_steps["roll back the AgentCore runtime"]
    assert job_steps["record the live release"]["id"] == "record"
    assert rollback["if"] == "failure() && steps.record.outcome == 'success'"
    assert "infra/scripts/rollback-agent-runtime.sh" in rollback["run"]
    assert '"$agentcore_note"' in rollback["run"]
    assert "rollback-agent-runtime.sh" not in job_steps["roll back"]["run"]


def test_the_docs_describe_the_runtime_image_and_its_rollback() -> None:
    docs = PIPELINE_DOCS.read_text("utf-8")
    assert "<sha>-agent-runtime" in docs
    assert "rollback-agent-runtime.sh" in docs
    assert "ubuntu-24.04-arm" in docs
