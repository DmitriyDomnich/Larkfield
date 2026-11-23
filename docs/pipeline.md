# Pipeline

How code gets from a pull request to AWS. Spec: [T14](../specs/T14-deployment-ci-cd.md).

| Workflow | Runs on | Does |
|---|---|---|
| `ci.yml` (CI) | every pull request into `dev` or `main`; called by the deploy | checks the code, the workflows and the Terraform |
| `deploy.yml` | push to `dev` (→ `dev`) or `main` (→ `prod`) | CI, then image, Terraform, migration, ECS, frontend, smoke request |
| `environment.yml` | by hand | Start / Stop an environment |

GitHub holds no AWS keys. Jobs that need AWS run in the GitHub environment `dev` or `prod`
(branch `dev` / `main` only) and get a 1-hour session of `larkfield-<env>-deploy` through OIDC. It
may apply its environment, deploy, and write its state. It is created by the
`infra/terraform/bootstrap` root, which an admin applies from a laptop.

## `ci.yml`: CI

Runs on `pull_request` into `dev`/`main`, and as a `workflow_call` from `deploy.yml`, so a merge
commit is checked again before it ships. All jobs run in parallel and none touches AWS. Unnamed steps (checkout, tool setup, `uv sync`, `npm ci`) only install.

### `lint`

| Step | What | Why | If it fails |
|---|---|---|---|
| `ruff check` | lint rules from `pyproject.toml` (bugs, security, imports) | catches mistakes before review | fix the reported lines (`make fmt` fixes most) |
| `ruff format` | formatting check | one style, no formatting diffs in reviews | run `make fmt` |

### `typecheck`

| Step | What | Why | If it fails |
|---|---|---|---|
| `mypy` | strict type check of `app`, `tests`, `migrations`, `lambdas`, `evals` | the project rule: fully typed | fix the types; don't add `ignore`s to get green |

### `test`

| Step | What | Why | If it fails |
|---|---|---|---|
| `all tests with coverage` | every test, unit and `integration` (a PostgreSQL 17 service), coverage of `app` with `fail_under = 80` | the merge gate for behaviour | a test or the coverage floor failed: the output names which |

### `evals`

| Step | What | Why | If it fails |
|---|---|---|---|
| `evals against fakes` | `pytest tests/evals --no-cov`: scoring, the recorded runs' reports and injection cases, the run loop with fakes; no AWS | shows a broken eval as its own check (`test` runs them too) | an eval scorer or report changed behaviour |

### `frontend`

| Step | What | Why | If it fails |
|---|---|---|---|
| `eslint` | `npm run lint` | lint rules, incl. no `dangerouslySetInnerHTML` | fix the lines |
| `tsc` | `npm run typecheck` | the frontend is typed against the API schema | fix the types |
| `vitest` | `npm test` | component, hook, CSP and client tests | a test failed |
| `generated API types match openapi.json` | regenerates `src/api/schema.d.ts` and diffs it | the client must match the API | run `make openapi` and commit the result |
| `build with the placeholder values of .env.example` | `next build` (static export) | the export must build; the deploy builds with real values | a build error in the frontend |

### `actionlint`

| Step | What | Why | If it fails |
|---|---|---|---|
| `lint the workflows` | `actionlint` (incl. shellcheck) on `.github/workflows/*.yml` | a broken workflow only shows when it runs, possibly mid-deploy | fix the reported workflow line |

### `terraform`

Once per root: `bootstrap`, `environments/dev`, `environments/prod`. No AWS access.

| Step | What | Why | If it fails |
|---|---|---|---|
| `terraform fmt` | `terraform fmt -check` of all of `infra/terraform` | one style | run `terraform fmt -recursive infra/terraform` |
| `terraform validate` | `init -backend=false` + `validate` | syntax, references, provider schemas | fix the reported resource |

## `deploy.yml`: Deploy

Runs on a push to `dev` (deploys `dev`) or `main` (deploys `prod`), and when the Environment
workflow dispatches it after a Start or Stop. One deploy per branch at a time; a newer one waits.

### `ci`

The whole of `ci.yml` on the pushed commit, so what ships is the merge commit that was checked,
not just the PR branch. Skipped when the Environment workflow dispatched the run (nothing new to
check). If it fails, nothing is deployed.

### `deploy`

Runs in the GitHub environment of the branch (`dev` / `prod`) and assumes that environment's
deploy role. The first six steps always run; the rest only while the environment is running
(`runtime_enabled`). Logs of the tasks: CloudWatch log groups `/ecs/larkfield-<env>/<task>`.

| Step | What | Why | If it fails |
|---|---|---|---|
| `assume the deploy role` | OIDC → `larkfield-<env>-deploy` (1 hour) | AWS access without stored keys | the environment variable `AWS_ROLE_ARN` is missing, `bootstrap` isn't applied, or the run isn't on `dev`/`main` |
| `image to ECR` | `infra/scripts/push-image.sh`: builds the image, pushes `larkfield-<env>:<sha>`; skips an existing tag | the services and the migration run this exact image | a Docker build error; on the very first deploy it only notes that the repository doesn't exist yet |
| `build the clause files` | `make kb-build` → `build/kb-clauses` | Terraform uploads them to the clause KB's bucket | a clause file couldn't be built from `inputs/kb` |
| `terraform variables` | `infra/scripts/terraform-vars.sh`: tfvars from the environment variable `TFVARS`, `runtime_enabled` from SSM, `restore_db_snapshot`, `image_tag` | Terraform gets what `terraform.tfvars` gives it locally; Start/Stop decide the runtime, not the push | `TFVARS` isn't valid JSON, or SSM can't be read |
| `terraform apply` | applies the environment root; registers new task definition revisions with the image | infrastructure changes ship through the pipeline only | read the Terraform error; the state is unchanged for anything that failed. A held lock waits 10 min |
| `image to ECR (first deploy)` | the push again, only if the repository didn't exist before the apply | the repository is created by Terraform | as `image to ECR` |
| `read the terraform outputs` | cluster, services, task families, KB ids, site bucket, distribution, `NEXT_PUBLIC_*` into the job's environment | the later steps address what Terraform created | an output is missing from the root |
| `sync the policy knowledge base` | `start-ingestion-job` on the `clause` data source, waits for `COMPLETE` | the review agent searches the policy text that was just uploaded; unchanged files cost nothing | the ingestion job failed: see it in the Bedrock console |
| `note a stopped environment` | a note in the run summary | a push while stopped only applies the base and pushes the image | never fails |
| `record the live release` | the services' current task definition revisions and the frontend release in `live/release.txt` | what a rollback restores | a service is missing (the apply didn't create it) |
| `run the migration` | `alembic upgrade head` as a one-off ECS task with the new image; must exit 0 | the new code expects the new schema; migrations are forward-only and backward compatible | the migration failed: its log is in `/ecs/larkfield-<env>/migrate`; nothing was deployed |
| `deploy the API and workers` | points each service at the revision the apply registered, waits for steady state, checks the new revision stayed | rolls out the image; the circuit breaker puts the old revision back if new tasks don't start or fail `/health` | the circuit breaker rolled a service back (the app is still on the old version): see the service's events and task logs |
| `release the frontend` | `next build` with the environment's values, uploads to `releases/<sha>/`, copies it to `live/`, invalidates CloudFront | the site is served from `live/`; keeping each release makes a rollback a copy | a build or upload error; the old release is still live |
| `smoke request` | through CloudFront, for up to 3 minutes: `GET /api/health` must say `database: ok`, `GET /` must return the app | proves the whole path a user takes: CloudFront → VPC origin → ALB → new API task → RDS | the new release doesn't serve: `roll back` runs |
| `roll back` | only after a failed smoke request: the recorded revisions back on the services, the recorded frontend release back in `live/`; the run fails | the app doesn't stay broken until someone reverts | the recorded release couldn't be restored: follow the rollback runbook |

## `environment.yml`: Environment (Start / Stop)

Run by hand from the Actions tab on `dev` (for `dev`) or `main` (for `prod`), input `start` or
`stop`. Shares the deploy's queue, so it never runs during a deploy.

### `switch`

| Step | What | Why | If it fails |
|---|---|---|---|
| `assume the deploy role` | OIDC → `larkfield-<env>-deploy` | as in the deploy | as in the deploy |
| `drop the previous snapshot` | Stop only, and only while the database exists: deletes `larkfield-<env>-latest` | the stop's final snapshot reuses that name; on a stopped environment it is the only copy, so it stays | the snapshot couldn't be deleted; nothing was stopped |
| `switch the runtime flag` | writes `true`/`false` to SSM `/larkfield-<env>/runtime_enabled` | every deploy reads the flag, so a push never starts or stops an environment | SSM write denied: check the deploy role |
| `run the deploy` | `gh workflow run deploy.yml` on the same branch | the deploy applies the change: Start creates NAT, RDS (from the snapshot), ALB, VPC origin and services, then deploys the branch's newest commit; Stop snapshots RDS and removes them | the dispatch failed: run the Deploy workflow by hand |

Start takes about 10–15 minutes; a stopped environment costs about $1–3/month.

## Runbooks

### Bootstrap (once per AWS account)

You need: admin credentials for the account, Terraform ≥ 1.11, the existing state bucket (the one
in `environments/dev/backend.hcl`), the `gh` CLI.

1. If you attached the pre-T14 `larkfield-dev-*` policies to an IAM user for local work, detach
   them: the first deploy replaces them (they move under `/larkfield-dev/`).
2. Apply `bootstrap` from your laptop:

   ```sh
   cd infra/terraform/bootstrap
   cp backend.hcl.example backend.hcl            # state bucket + region
   cp terraform.tfvars.example terraform.tfvars  # region, owner/repo, state bucket
   terraform init -backend-config=backend.hcl
   terraform apply
   terraform output deploy_role_arns
   ```

   From now on a laptop `terraform apply` of `dev` or `prod` fails on the state lock (a `plan`
   still works).
3. GitHub, in Settings → Environments: create `dev` (deployment branch: `dev`) and `prod`
   (deployment branch: `main`), each with the variables `AWS_ROLE_ARN` (from the output) and
   `TFVARS` (your `terraform.tfvars` as JSON, plus `alarm_email`). Repo variables: `AWS_REGION`,
   `TF_STATE_BUCKET`. The variables with `gh`, once the environments exist:

   ```sh
   gh variable set AWS_ROLE_ARN --env dev --body "<dev deploy role ARN>"
   gh variable set TFVARS --env dev < dev-tfvars.json
   # the same for prod with branch main
   gh variable set AWS_REGION --body "<region>"
   gh variable set TF_STATE_BUCKET --body "<state bucket>"
   ```

4. Branch protection on `dev` and `main`: pull request required, the CI checks required.
5. Merge to `dev`: the first deploy applies the base (environment stopped) and moves the IAM roles.
   Confirm the SNS subscription email (`alarm_email`). Then Start `dev`.

Changing a deploy role or the boundary later: edit `bootstrap`, apply it again from a laptop.

### Start / Stop

- Actions → Environment → Run workflow → branch `dev` or `main` → `start` / `stop`, or
  `gh workflow run environment.yml --ref dev -f action=start`.
- The run dispatches a Deploy run that does the work; follow that one.
- Until `environment.yml` is on `main` (GitHub only offers dispatch for workflows on the default
  branch), switch by hand: `aws ssm put-parameter --name /larkfield-dev/runtime_enabled --type String
  --value true --overwrite`, then `gh run rerun <id of the last Deploy run on dev>`. For a stop by
  hand, delete an existing `larkfield-dev-latest` snapshot first, but only while the database exists.
- Messages that arrive while stopped wait in SQS (4 days; 14 in the DLQs) and are processed after
  a Start.

### Rollback

- **A new task doesn't start or fails `/health`:** the circuit breaker puts the old revision back;
  the deploy fails at `deploy the API and workers`. Nothing to do but fix the commit.
- **The smoke request fails:** the deploy's `roll back` step restores the services' previous
  revisions and the previous frontend release, then fails the run.
- **A problem found later:** revert the commit with a PR; its deploy ships the previous code. To
  go back faster, re-run the last good Deploy run (`gh run rerun <id>`): it redeploys that
  commit's image, infrastructure and frontend.
- **Schema:** never rolled back. Migrations must stay backward compatible (expand, deploy, contract
  later), so the previous image runs on the new schema. A broken migration is fixed forward.
