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
