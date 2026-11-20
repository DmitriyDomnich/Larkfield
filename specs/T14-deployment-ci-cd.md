# T14 — Deployment and CI/CD

**Goal:** a merge to main reaches AWS without manual steps. **Out of scope:** deploying the MCP server
(local stdio debugging tool, T10), a custom domain, separate AWS accounts per environment,
Multi-AZ / high availability, automatic secret rotation.

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| A merge to main builds, deploys and runs a smoke request without manual steps | `deploy.yml` on push to `main` (→ `prod`) or `dev` (→ `dev`): CI, image to ECR, `terraform apply`, KB ingestion, migration task, ECS deploy of API + workers, frontend release, smoke `GET /api/health` + `GET /` through CloudFront; a failed smoke rolls back. Stopped environment: base + image only, noted in the summary | `tests/test_workflows.py` (triggers, job order, environment per branch); manual run on `dev` and `prod` (Results) |
| Pull requests run lint, type check, tests with coverage ≥ 80%, evals against fakes, and frontend lint and type check | `ci.yml` on `pull_request` + `workflow_call`: `lint`, `typecheck`, `test` (`fail_under = 80`), `evals` (`tests/evals`), `frontend`, `actionlint`, `terraform` (validate + read-only plan) | `tests/test_workflows.py` (jobs present, PR trigger); the PR's own checks |
| GitHub holds no long-lived AWS keys | GitHub OIDC → `<project>-<env>-deploy`, `<project>-<env>-plan`, trusted per repo + environment / event; 1-hour sessions; repo secrets hold no AWS values | `tests/test_workflows.py` (every `configure-aws-credentials` uses `role-to-assume`, no `aws-access-key-id`, `id-token: write` only on jobs that assume a role); manual: `gh secret list` empty of AWS keys |
| Infrastructure changes deploy through the pipeline, not from a laptop | `deploy.yml` applies the environment roots; the state bucket policy lets only each deploy role write its state and lock; `Start`/`Stop` are workflows; `bootstrap` is the one admin-applied root | manual: a local `terraform apply` on `dev` fails on the lock; `tests/test_workflows.py` |
| docs/pipeline.md describes every pipeline step and why it is there | One section per workflow, one entry per job/step: what, why, what failing means. Bootstrap, start/stop and rollback runbooks | `tests/test_workflows.py`: every job id and step `name` in `.github/workflows/*.yml` appears in `docs/pipeline.md` |
| An alarm fires on failed claims; Bedrock tokens per claim are visible as a metric | EMF lines from the workers: `ClaimsFailed{Stage}` → alarm → SNS email; `BedrockInputTokens`/`OutputTokens{Stage}` per claim on the `<project>-<env>` dashboard; DLQ alarms | `tests/core/test_metrics.py`, `tests/extraction/test_worker_db.py`, `tests/review/test_review_db.py`; manual: an invalid upload → `failed` → alarm email |

## Flow

```mermaid
sequenceDiagram
    participant GH as GitHub (push to dev/main)
    participant CI as ci.yml
    participant D as deploy.yml (OIDC → deploy role)
    participant AWS as Terraform / ECR / Bedrock KB
    participant ECS
    participant CF as CloudFront + S3
    GH->>CI: lint, typecheck, test ≥80%, evals, frontend, actionlint, terraform
    CI-->>D: green
    D->>AWS: image :sha → ECR; kb-build; terraform apply; ingestion job
    alt runtime stopped
        D-->>GH: summary "environment stopped, deploy skipped"
    end
    D->>ECS: record current revisions; run migration task (exit 0)
    D->>ECS: deploy API + workers, wait steady (circuit breaker rolls back)
    D->>CF: next build → releases/sha → live, invalidate
    D->>CF: smoke GET /api/health, GET /
    alt smoke fails
        D->>ECS: redeploy recorded revisions
        D->>CF: restore previous release; run fails
    end
```

## Design decisions

- **Two environments: `dev` branch → `environments/dev`, `main` → `environments/prod`.** Separate
  Terraform roots and state keys, same modules; each has its own GitHub environment (`dev`,
  `prod`) holding its non-secret variables (role ARN, region, tfvars values). *Rejected:* one
  environment deployed from main (no place to try a change before prod).
- **Stopped when idle: keep the base, toggle the runtime.** `runtime_enabled` (Terraform bool)
  creates or destroys only what bills by the hour: the ALB, the VPC origin and CloudFront's `/api/*`
  behavior, RDS, the ECS services and the NAT gateway with its Elastic IP. Cognito, the buckets, SQS, Lambdas, SES
  identities, the KBs, ECR, IAM and the CloudFront distribution stay, so users, verified emails and
  the URL survive. Stop deletes the previous `<project>-latest` snapshot and takes a new one as the
  instance's final snapshot; start restores from it (`restore_db_snapshot`, set by the workflows
  when that snapshot exists, since Terraform can't look it up without failing when it's missing;
  `snapshot_identifier` is ignored after create, so a deploy never replaces the database). `Start` and
  `Stop` are `workflow_dispatch` runs per environment that write `/<project>/runtime_enabled`
  (SSM) and apply; start then deploys the newest image of the branch. A push while the environment
  is stopped applies the base and pushes the image, then skips migrate/deploy/smoke with a notice in
  the run summary. About $1–3/month idle per environment, about 10–15 min to start. *Rejected:*
  full destroy (new pool and URL, SES re-verification, KB re-ingest, data lost), scale to zero (the
  ALB and NAT keep billing, about $55/month, and RDS auto-starts after 7 days).
- **Everything in private subnets, one NAT gateway, S3 gateway endpoint:** the API and both
  workers (no public IP), the internal ALB and RDS sit in private subnets; only the NAT gateway
  sits in a public subnet. Bedrock, SQS, Cognito (including the JWKS URL), ECR's API, Logs and
  Secrets Manager go through the NAT. S3 goes through a free gateway endpoint, so receipt
  downloads, upload checks and ECR image layers skip the NAT's per-GB charge
  ([S3 gateway endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html)).
  The NAT is part of the runtime toggle, so it bills only while the environment runs (about
  $0.05/h + $0.05/GB in eu-central-1). Security groups: the API admits only the ALB, the workers
  nothing, RDS only the tasks. *Rejected:* public subnets with task public IPs (tasks
  internet-addressable, guarded only by their security groups; per-task IPv4 charges), interface
  endpoints only (about 8 × 2 AZs ≈ $0.19/h, and the JWKS URL may still need a NAT), a NAT instance
  (an EC2 instance to patch).
- **Frontend hosting: one CloudFront distribution, the only entry point.** It serves the default
  behavior from a private S3 bucket (OAC), with a CloudFront Function mapping `/claims/view` to
  `claims/view.html`, and `404.html` for misses. `/api/*` goes to the API with the prefix stripped
  by a function, so the API keeps its paths. The browser sees one HTTPS origin
  (`*.cloudfront.net`, no domain needed): no CORS for the API, `connect-src 'self'`. A
  response-headers policy adds a CSP header with only `frame-ancestors 'none'` (which a `<meta>` CSP
  can't set), HSTS and `nosniff`, which closes T13's header gap. The browser enforces the header and
  the page's `<meta>` CSP together, so the header leaves `connect-src` etc. to the meta (Cognito and
  the documents bucket must stay reachable). The bucket's CORS lists the distribution's origin for the presigned
  upload. *Rejected:* two distributions (CORS and a second origin in the CSP), a custom domain + ACM
  on the ALB (no domain), Amplify Hosting (builds outside our pipeline, doesn't front the API).
- **API origin: CloudFront VPC origin to an internal ALB.** The ALB sits in private subnets with no
  public address. CloudFront reaches it through a service-managed ENI over AWS's network, and the
  ALB's security group admits only CloudFront's service-managed group, so only our distribution
  gets in ([VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html)).
  *Rejected:* a public ALB on HTTP behind a prefix list + secret header (tokens and receipts in
  cleartext on the internet between edge and origin).
- **Terraform for infrastructure, ECS actions for the app:** images go to ECR tagged with the git
  SHA (immutable tags). Terraform owns the cluster, services and a base task definition per service
  (`lifecycle { ignore_changes = [task_definition] }`). The deploy job runs `terraform apply`, then
  the migration task (`alembic upgrade head`, new image, one-off `run-task`, must exit 0), then
  `amazon-ecs-render-task-definition` + `amazon-ecs-deploy-task-definition` for the API and both
  workers, waiting for steady state. *Rejected:* Terraform deploying the image too (migrations need
  to run between infrastructure and rollout, which takes two applies; an ECS rollback drifts the
  state), ECS blue/green (the workers have no traffic to shift).
- **Rollback: circuit breaker, then auto-rollback on a failed smoke request.** Each service has the
  deployment circuit breaker with `rollback = true`, so new tasks that don't start or fail the
  ALB's `/health` check put the previous revision back
  ([circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html)).
  Before deploying, the job records each service's current task-definition revision and the live
  frontend release. If the smoke request then fails, it redeploys those revisions, restores that
  frontend release, and fails the run. The frontend is kept per release in
  `site/releases/<sha>/` and copied to `site/live/` (CloudFront's origin path) with an
  invalidation, so restoring is a copy. Migrations are forward-only and backward-compatible
  (expand, deploy, contract in a later release), so the previous image runs on the new schema; the
  schema itself is never rolled back. A `git revert` on main is the permanent fix. *Rejected:*
  circuit breaker only (a failed smoke test leaves the app broken until someone reverts), blue/green
  with bake time (more plumbing, nothing for the workers).
- **Deploy role scoped by a permissions boundary, trust anchor in `bootstrap`:** see Questions.
  `infra/terraform/bootstrap` (OIDC provider, the deploy roles, the boundary) is applied once by an
  admin from a laptop, the one documented exception: it is what lets the pipeline in, so the
  pipeline can't be allowed to change it. Existing roles and policies move under the IAM path
  (replaced once, with the boundary attached). The new roles need the boundary, which only exists
  after `bootstrap`, so `bootstrap` is applied first and the first pipeline deploy of `dev` does the
  move: besides its path, the deploy role may only *delete* the old root-path roles and policies
  named `<project>-<env>-*` (no create, change or pass; its own and the plan role are explicit
  denies). *Rejected:* an admin moving them from a laptop (three steps with `-target`, since the
  state bucket policy blocks laptop writes once `bootstrap` is applied). *Rejected:* `AdministratorAccess` (it can rewrite its own policy, so merging to
  main means owning the account), `PowerUserAccess` + IAM (escalation reopens unless boundaries are
  added anyway).
- **`terraform plan` on PRs with a read-only role:** `<project>-<env>-plan`, trusted for
  `repo:…:pull_request` (same-repo branches only; forks get no OIDC token). It can describe/list,
  read its state key and write only the `.tflock`. Its only other object reads are the policies and
  clauses buckets (policy text; refreshing `aws_s3_object` calls HeadObject, which needs
  `s3:GetObject`), never the documents or site bucket, and no secret values (with
  `secret_string_wo` the provider refreshes the version through `ListSecretVersionIds` only). The
  PR plans against the environment its base branch deploys to, and the plan goes to the job
  summary. The plan job declares no GitHub environment (that would change the OIDC `sub` to
  `environment:<env>`, and the environment's branch rule rejects PR refs), so what it needs lives
  in repo variables (Configuration). *Rejected:* no AWS on PRs (the first plan anyone sees is the one being
  applied), plan behind a label (solo repo).
- **DB password write-only, never in state:** an `ephemeral "random_password"` is written once to a
  base Secrets Manager secret (`secret_string_wo`, a new value only when `db_password_version`
  changes). The secret is the source of truth: RDS reads it through an ephemeral
  `aws_secretsmanager_secret_version` into `password_wo` (+ `password_wo_version`), so an
  instance created by any later Start, or restored from the snapshot, gets the same value. Neither
  the state nor the plan contains it. The PR plan passes `apply_db_password = false` (its role can't
  read the secret; write-only values never show in a plan anyway). ECS injects it as
  `PGPASSWORD`, and libpq uses it because `DATABASE_URL` has none, so no code change. The secret
  survives stop/start and matches the restored snapshot. *Rejected:* the random value written to
  both the secret and RDS in one apply (RDS is created in a later apply than the secret, with a
  new random value the secret doesn't hold), the RDS-managed password
  (7-day rotation breaks running tasks; deleted with the instance on stop; can't be set on a
  PostgreSQL snapshot restore), `random_password` (in state).
- **Metrics as Embedded Metric Format log lines:** a small `app/core/metrics.py` prints one EMF
  JSON line to stdout, and the `awslogs` driver ships it, so CloudWatch extracts the metric
  ([EMF](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html)).
  Namespace `Larkfield/<env>`, dimension `Stage` (`extraction` | `review`); `claim_id` is a property
  (searchable in Logs Insights, not a dimension).
  - `ClaimsFailed` (count 1), where both workers already call `notify_claim_failed`, so every path
    to `failed` (upload checks, extraction, review) is counted once.
  - `BedrockInputTokens`, `BedrockOutputTokens` once per claim per stage: extraction sums
    Converse's `usage` over its attempts, review takes Strands' `result.metrics.accumulated_usage`.
    "Per claim" is the Average / p90 statistic; a dashboard `<project>-<env>` shows both stages and
    their sum.

  No IAM, no extra API call, nothing blocking. *Rejected:* `PutMetricData` (an IAM grant and a call
  per claim that can fail), metric filters on log text (they break when a message is reworded).
- **Alarms by email:** one SNS topic per environment, with an email subscription (`alarm_email`,
  confirmed once). `ClaimsFailed` Sum ≥ 1 in 5 minutes, and any visible message in the extraction,
  review or notification DLQ (closes T12's DLQ gap), with missing data treated as OK. The alarms live
  with the runtime, so a stopped environment never alarms. *Rejected:* failed claims only (DLQs
  unwatched), no target (nobody is told).
- **CI is reused by the deploy:** `ci.yml` runs on `pull_request` and as a `workflow_call`.
  `deploy.yml` (push to `dev`/`main`) calls it first, so the merge commit itself is tested before
  it ships. The evals against fakes (`tests/evals`: scoring, the recorded runs' reports and
  injection cases, the run loop with `review_fakes`) get their own `evals` job
  (`pytest tests/evals --no-cov`), so a failing eval shows as its own check; `test` still runs
  everything with `fail_under = 80`. `actionlint` checks the workflows; `terraform` validates
  `bootstrap`, `dev` and `prod`, and plans `dev`/`prod`.
- **Laptop applies are blocked, not just discouraged:** the state bucket's policy (bootstrap)
  allows writing `dev/` and `prod/` state and locks only to that environment's deploy role (plan
  roles: the `.tflock` only), so a local `terraform apply` fails on the lock. Local `plan` still
  works for an admin. `bootstrap/` stays writable by an admin only.
- **Policy KB synced by the pipeline:** the deploy runs `make kb-build` before `terraform apply` (the
  module uploads `build/kb-clauses`), then `start-ingestion-job` on the clause data source and waits
  for `COMPLETE`. Ingestion is incremental, so unchanged files cost nothing. Prod creates only the
  `clause` KB; the other chunking strategies stay eval-only in dev.
- **Smoke request:** through CloudFront, as a user would: `GET /api/health` must return 200 with
  `database: ok` (CloudFront → VPC origin → ALB → a new API task → RDS), and `GET /` must return
  the app shell, retried for up to 3 minutes. The workers have no endpoint: a worker that can't
  start fails steady state and trips its circuit breaker.

## Questions

- **What can the deploy role do?** One role per environment, `<project>-<env>-deploy`, assumed only
  through GitHub OIDC with `aud = sts.amazonaws.com` and
  `sub = repo:DmitriyDomnich/Larkfield:environment:<env>`. The GitHub environment's branch rule
  allows `prod` only from `main` and `dev` only from `dev`, so a feature branch or PR can't assume
  it ([GitHub OIDC in AWS](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)).
  Sessions last 1 hour. It may manage the services Terraform uses (VPC/EC2 networking, ECS, ECR,
  RDS, ELB, CloudFront, S3, SQS, Lambda, Cognito, SES, Bedrock/KB, S3 Vectors, CloudWatch, SNS, SSM,
  Secrets Manager), on resources named `<project>-<env>-*` where the service supports
  resource-level conditions. It may read and write only its own state key. In IAM it may create,
  change and pass roles and policies only under the path `/<project>-<env>/`, only with the
  permissions boundary `<project>-<env>-boundary` attached (`iam:PermissionsBoundary` condition),
  and pass them only to `ecs-tasks`, `lambda` and `bedrock`.
- **Could it grant itself more permissions?** Not directly. Its own role, the boundary policy, the
  OIDC provider and the `bootstrap/` state key are explicit denies, and it has no
  `iam:CreateUser`/`CreateAccessKey`. Those live in the `bootstrap` root, applied by an admin. Any
  role it creates is capped by the boundary, which allows the app's actions and denies all of IAM,
  so a Lambda or task it launches can't escalate either
  ([permissions boundaries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)).
  The uncomfortable part: within its environment it can do anything the app can, plus delete it.
  It can read every receipt and secret, drop the database, or run code as a boundary-capped role.
  So whoever can push to `main` (or `dev`) holds that power, and branch protection with a required
  PR and green CI on both branches is part of the control. Dev's role can't touch prod: name
  prefixes where the ARN has a name, a separate state key, and for services addressed by id (EC2,
  CloudFront, Cognito, SES, Bedrock) an explicit deny on any resource or request tagged with
  another `Environment` (every resource carries its root's `default_tags`). Both share one
  account, though; separate accounts would make that a hard boundary (Known gaps). The pipeline
  roles, their policies and the boundaries sit under the IAM path `/<project>-bootstrap/`, outside
  every environment's path.

## Configuration

- **Terraform `infra/terraform/bootstrap`** (admin, once): GitHub OIDC provider; per environment
  the `deploy` and `plan` roles and the `boundary` policy; the state bucket (imported) and its
  policy. Variables: `github_repo`, `environments`, `state_bucket`.
- **`environments/prod`:** a new root like `dev`, state key `prod/terraform.tfstate`, only the
  `clause` KB, Cognito with `enable_password_auth = false`.
- **New modules:** `network` (VPC, 2 public + 2 private subnets, IGW, S3 gateway endpoint on the
  private route tables; NAT gateway + Elastic IP in one public subnet and the private default route,
  both behind `runtime_enabled`), `database` (RDS PostgreSQL
  17, `db.t4g.micro`, single-AZ, 20 GB gp3, 1-day backups, write-only password + secret, snapshot
  on stop / restore on start), `runtime` (ECR with immutable tags + a lifecycle keeping 20 images,
  ECS cluster, task roles from the existing policy ARNs, services: API 0.5 vCPU / 1 GB, workers
  0.25 vCPU / 0.5 GB extraction and 0.5 / 1 GB review, 1 task each, circuit breaker; internal ALB;
  migration task definition; log groups with 14-day retention), `edge` (site bucket, CloudFront
  with OAC, the VPC origin, the two functions, response-headers policy), `monitoring` (SNS + email,
  alarms, dashboard).
- **Terraform `>= 1.11`** (ephemeral resources and write-only arguments); the AWS provider stays `~> 6.0`.
- **Naming:** `<project>` is `larkfield`; a new `environment` variable (`dev` | `prod`) makes the
  resource prefix `larkfield-<env>`, which is today's `project_name` in dev, so no existing resource
  is renamed. SSM `/larkfield-<env>/runtime_enabled`, snapshot `larkfield-<env>-latest`, IAM path
  `/larkfield-<env>/`, roles `larkfield-<env>-deploy|plan`, metrics namespace `Larkfield/<env>`.
- **New variables:** `environment`, `runtime_enabled` (also SSM `/larkfield-<env>/runtime_enabled`),
  `alarm_email`, `db_password_version`, `restore_db_snapshot`, `apply_db_password`, `image_tag`
  (the SHA the deploy pushed; the base task definitions point at it). `frontend_origins` becomes the distribution's origin (+ localhost in
  dev). IAM roles and policies move under `/<project>-<env>/`.
- **Task environment:** what compose sets today, from Terraform outputs; `APP_ENV` = `dev`/`prod`,
  `DATABASE_URL` without a password, `PGPASSWORD` from the secret, `FRONTEND_ORIGINS` = the
  distribution's origin. No new `Settings` fields.
- **Frontend build:** `NEXT_PUBLIC_API_URL = https://<distribution>/api` and the other
  `NEXT_PUBLIC_*` from Terraform outputs in the deploy job.
- **GitHub:** environments `dev` (branch `dev`) and `prod` (branch `main`), each holding only
  `AWS_ROLE_ARN` (the deploy role). Repo variables, readable by the PR plan job too: `AWS_REGION`,
  `TF_STATE_BUCKET`, `DEV_PLAN_ROLE_ARN`, `PROD_PLAN_ROLE_ARN`, `DEV_TFVARS`, `PROD_TFVARS` (JSON of
  today's `terraform.tfvars` values: sender/recipient/alarm emails, inference profiles; written to
  `ci.auto.tfvars.json` by both plan and deploy). No secrets. Branch protection on `main` and `dev`: PR required, CI green.
- **Workflows:** `ci.yml` (changed: `pull_request` + `workflow_call`, new `evals`, `actionlint`,
  plan), `deploy.yml`, `environment.yml` (Start/Stop).
- **Code:** `app/core/metrics.py`, calls in both workers, `docs/pipeline.md`; `pyyaml` as a dev
  dependency for `tests/test_workflows.py`.

## Known gaps

- `bootstrap` is applied from a laptop by an admin; changing the deploy roles or the boundary is
  manual by design.
- The deploy role can delete the pre-T14 root-path roles and policies named `<project>-<env>-*`
  (needed once, for the move); deleting is within what it can already do to its environment.
- The PR plan role can read the policy and clause files (needed to refresh their `aws_s3_object`s).
- Dev and prod share one AWS account: the boundary and name prefixes separate them, but an IAM
  mistake in a boundary affects both. Separate accounts would make it a hard boundary.
- Whoever can merge to `main` can do anything the prod deploy role can (read every receipt, delete
  the environment); branch protection is the control. Admins can bypass it.
- Rollback restores code, not schema: a migration that isn't backward-compatible breaks the
  previous image too. Recovery: a forward fix.
- The VPC-origin hop from CloudFront to the ALB is HTTP inside AWS; end-to-end TLS needs a domain.
- `'unsafe-inline'` stays in `script-src` (the static export's inline scripts, T13).
- Single-AZ RDS, one NAT gateway and one task per service: an AZ outage (for the NAT, its AZ cuts
  every task off from Bedrock, SQS and Cognito) or a task restart means downtime. Fine for a demo;
  prod would use Multi-AZ, a NAT per AZ and two API tasks.
- Stop/start loses nothing in the DB but takes about 10–15 min to start; RDS snapshots bill for
  storage. Messages arriving while stopped wait in SQS (4-day default retention, 14 for DLQs).
- No password rotation: rotating means bumping `db_password_version` and redeploying.

## Testing

- **Unit:** the EMF line (namespace, dimensions, units, `claim_id` property); workers emit
  `ClaimsFailed` on each failure path and one token metric per claim per stage (fake Bedrock and
  agent results); `tests/test_workflows.py` parses the workflows: triggers, job graph, environment
  per branch, OIDC only, no AWS keys, the `evals` job, and every job/step
  documented in `docs/pipeline.md`.
- **Integration:** the existing worker DB tests extended with the metric assertions
  (`tests/extraction/test_worker_db.py`, `tests/review/test_review_db.py`).
- **Manual:** apply `bootstrap`; merge to `dev`, watch the deploy reach the smoke request; push a
  commit whose API fails `/health`, see the circuit breaker roll back; break the smoke request (bad
  CloudFront path), see the job restore the revisions and frontend; a local `terraform apply`
  fails on the lock; an invalid upload → `failed` → alarm email, and tokens on the dashboard
  after a claim reaches `in_review`; Stop, then Start, data still there; merge to `main` → prod.

## Results

## Commit plan

- [x] 1. EMF metrics module; `ClaimsFailed` on every path to `failed` and Bedrock token metrics once per claim per stage in both workers — alarm/tokens (code part) — `add emf metrics module, claims failed and bedrock token metrics per claim from both workers, tests`
- [x] 2. `bootstrap` root: GitHub OIDC provider, per-environment deploy and plan roles with the permissions boundary, imported state bucket and its policy; Terraform `>= 1.11`; existing roles and policies under `/<project>-<env>/` — no long-lived keys, infra through the pipeline — `add terraform bootstrap root with github oidc, deploy and plan roles, permissions boundary, state bucket policy, iam paths`
- [x] 3. `network`, `database`, `runtime` modules behind `runtime_enabled`, wired into `dev`: VPC, NAT, S3 endpoint, RDS with write-only password, ECR, ECS cluster + services + migration task, internal ALB — merge deploys (infra) — `add network, database and runtime terraform modules behind the runtime toggle, wire into dev`
- [ ] 4. `edge` and `monitoring` modules, `environments/prod`: site bucket, CloudFront with OAC, VPC origin, functions, headers policy; SNS, alarms, dashboard — merge deploys (infra), alarm/tokens (infra) — `add edge and monitoring terraform modules, prod environment root`
- [ ] 5. `ci.yml` on `pull_request` + `workflow_call` with `evals`, `actionlint`, terraform validate of every root + read-only plan; `tests/test_workflows.py`, `docs/pipeline.md` CI section, `pyyaml` — PR checks, docs, no long-lived keys — `add evals, actionlint and terraform plan ci jobs, reusable ci, workflow tests, pipeline docs`
- [ ] 6. `deploy.yml` and `environment.yml` (Start/Stop), runbooks (bootstrap, start/stop, rollback), workflow tests — merge deploys, infra through the pipeline, docs, no long-lived keys — `add deploy workflow with migration, ecs deploy, frontend release, smoke and rollback, start/stop workflow, runbooks, tests`
