import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path("infra/scripts").resolve()
BASH = shutil.which("bash") or "/bin/bash"

# stands in for the AWS CLI: each command answers per its FAKE_* variable
FAKE_AWS = r"""#!/usr/bin/env bash
echo "aws $*" >> "$CALLS"
answer() {
  case "$1" in
    found) echo "${2:-found}" ;;
    missing) echo "An error occurred ($3) when calling the operation" >&2; exit 254 ;;
    *) echo "An error occurred (ThrottlingException): Rate exceeded" >&2; exit 254 ;;
  esac
}
case "$1 $2" in
  "ssm get-parameter") answer "$FAKE_PARAMETER" "$FAKE_PARAMETER_VALUE" ParameterNotFound ;;
  "rds describe-db-snapshots") answer "$FAKE_SNAPSHOT" "" DBSnapshotNotFound ;;
  "ecr describe-repositories") answer "$FAKE_REPOSITORY" "" RepositoryNotFoundException ;;
  "ecr describe-images") answer "$FAKE_IMAGE" "" ImageNotFoundException ;;
  "sts get-caller-identity") echo 123456789012 ;;
  *) ;;
esac
"""


@pytest.fixture
def fake_tools(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in {"aws": FAKE_AWS, "docker": 'echo "docker $*" >> "$CALLS"\n'}.items():
        tool = bin_dir / name
        tool.write_text(script if script.startswith("#!") else f"#!/usr/bin/env bash\n{script}")
        tool.chmod(0o755)
    return tmp_path


def run_script(name: str, workdir: Path, **env: str) -> subprocess.CompletedProcess[str]:
    variables = {
        "PATH": f"{workdir / 'bin'}:{os.environ['PATH']}",
        "CALLS": str(workdir / "calls.txt"),
        "GITHUB_OUTPUT": str(workdir / "output.txt"),
        "ENVIRONMENT": "dev",
        **env,
    }
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPTS / name)],
        cwd=workdir,
        env=variables,
        capture_output=True,
        text=True,
        check=False,
    )


def terraform_vars(workdir: Path, **fakes: str) -> subprocess.CompletedProcess[str]:
    return run_script(
        "terraform-vars.sh",
        workdir,
        TFVARS='{"aws_region": "eu-central-1"}',
        EXTRA_VARS='{"image_tag": "abc123"}',
        **fakes,
    )


def pipeline_vars(workdir: Path) -> dict[str, object]:
    result: dict[str, object] = json.loads((workdir / "pipeline.auto.tfvars.json").read_text())
    return result


def test_a_never_started_environment_is_stopped_and_has_nothing_to_restore(
    fake_tools: Path,
) -> None:
    result = terraform_vars(fake_tools, FAKE_PARAMETER="missing", FAKE_SNAPSHOT="missing")

    assert result.returncode == 0, result.stderr
    assert pipeline_vars(fake_tools) == {
        "runtime_enabled": False,
        "restore_db_snapshot": False,
        "image_tag": "abc123",
    }
    assert json.loads((fake_tools / "ci.auto.tfvars.json").read_text()) == {
        "aws_region": "eu-central-1"
    }
    assert "runtime_enabled=false" in (fake_tools / "output.txt").read_text()


def test_a_started_environment_restores_its_snapshot(fake_tools: Path) -> None:
    result = terraform_vars(
        fake_tools, FAKE_PARAMETER="found", FAKE_PARAMETER_VALUE="true", FAKE_SNAPSHOT="found"
    )

    assert result.returncode == 0, result.stderr
    assert pipeline_vars(fake_tools)["runtime_enabled"] is True
    assert pipeline_vars(fake_tools)["restore_db_snapshot"] is True


@pytest.mark.parametrize(
    "fakes",
    [
        {"FAKE_PARAMETER": "error", "FAKE_SNAPSHOT": "found"},
        {"FAKE_PARAMETER": "found", "FAKE_PARAMETER_VALUE": "true", "FAKE_SNAPSHOT": "error"},
    ],
    ids=["flag", "snapshot"],
)
def test_a_lookup_error_fails_instead_of_meaning_missing(
    fake_tools: Path, fakes: dict[str, str]
) -> None:
    """A throttled snapshot lookup read as "no snapshot" would start an empty database"""
    result = terraform_vars(fake_tools, **fakes)

    assert result.returncode != 0
    assert "ThrottlingException" in result.stderr
    assert not (fake_tools / "pipeline.auto.tfvars.json").exists()


def test_no_repository_yet_means_push_after_the_apply(fake_tools: Path) -> None:
    result = run_script(
        "push-image.sh",
        fake_tools,
        IMAGE_TAG="abc123",
        AWS_REGION="eu-central-1",
        FAKE_REPOSITORY="missing",
    )

    assert result.returncode == 0, result.stderr
    assert "pushed=false" in (fake_tools / "output.txt").read_text()


def test_a_new_tag_is_built_and_pushed(fake_tools: Path) -> None:
    result = run_script(
        "push-image.sh",
        fake_tools,
        IMAGE_TAG="abc123",
        AWS_REGION="eu-central-1",
        FAKE_REPOSITORY="found",
        FAKE_IMAGE="missing",
    )

    assert result.returncode == 0, result.stderr
    calls = (fake_tools / "calls.txt").read_text()
    image = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/larkfield-dev:abc123"
    assert f"docker build --tag {image} ." in calls
    assert f"docker push {image}" in calls
    assert "pushed=true" in (fake_tools / "output.txt").read_text()


def test_an_existing_tag_is_left_as_it_is(fake_tools: Path) -> None:
    result = run_script(
        "push-image.sh",
        fake_tools,
        IMAGE_TAG="abc123",
        AWS_REGION="eu-central-1",
        FAKE_REPOSITORY="found",
        FAKE_IMAGE="found",
    )

    assert result.returncode == 0, result.stderr
    assert "docker" not in (fake_tools / "calls.txt").read_text()


@pytest.mark.parametrize(
    "fakes", [{"FAKE_REPOSITORY": "error"}, {"FAKE_REPOSITORY": "found", "FAKE_IMAGE": "error"}]
)
def test_an_ecr_error_fails_the_push(fake_tools: Path, fakes: dict[str, str]) -> None:
    result = run_script(
        "push-image.sh", fake_tools, IMAGE_TAG="abc123", AWS_REGION="eu-central-1", **fakes
    )

    assert result.returncode != 0
    assert "docker" not in (fake_tools / "calls.txt").read_text()


def test_publishing_copies_every_object_before_removing_the_rest(fake_tools: Path) -> None:
    """A rollback goes to an older release; an S3-to-S3 sync would skip its same-size files"""
    result = run_script("publish-release.sh", fake_tools, SITE_BUCKET="site", DISTRIBUTION_ID="E1")
    assert result.returncode != 0  # the release SHA is required

    subprocess.run(  # noqa: S603
        [BASH, str(SCRIPTS / "publish-release.sh"), "abc123"],
        cwd=fake_tools,
        env={
            "PATH": f"{fake_tools / 'bin'}:{os.environ['PATH']}",
            "CALLS": str(fake_tools / "calls.txt"),
            "SITE_BUCKET": "site",
            "DISTRIBUTION_ID": "E1",
        },
        check=True,
        capture_output=True,
    )

    calls = (fake_tools / "calls.txt").read_text().splitlines()
    assert calls == [
        "aws s3 cp s3://site/releases/abc123 s3://site/live --recursive --only-show-errors",
        "aws s3 sync s3://site/releases/abc123 s3://site/live --delete --only-show-errors",
        "aws cloudfront create-invalidation --distribution-id E1 --paths /*",
    ]
