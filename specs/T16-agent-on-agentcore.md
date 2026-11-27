# T16 — Agent on Bedrock AgentCore Runtime

**Goal:** the agent runs on a managed agent runtime, deployed and scaled separately from the worker.
**Out of scope:** AgentCore Memory, Gateway, Identity and Observability traces; reviewing several
claims at once in one worker, or autoscaling the worker (T09 "Scaling" steps 1 and 3).

## Acceptance criteria

| Criterion | How | Tested by | Browser |
|---|---|---|---|
| The worker invokes the agent on Bedrock AgentCore Runtime; claims still end `in_review` or `failed` with a reason | `REVIEW_AGENT_RUNTIME_ARN` set → `AgentCoreClient`: claim + prefetched history → `InvokeAgentRuntime` (SigV4, session = claim id) → `runtime_app` runs `StrandsReviewAgent` → `proposal` / `no_proposal` / `error`; `review_claim` unchanged (proposal → `in_review`, none → `failed` + reason, errors → SQS retry, last delivery → `failed` + technical reason) | `tests/review/test_agentcore.py`, `test_runtime_app.py`, `test_runtime_contract.py`, `test_worker.py`; integration `test_review_db.py` | No |
| The review evaluation gives the same decisions as before, within the run-to-run variation measured | `make eval-review args="--agentcore"` on the 24 dev cases; every case except E02 matches `review-2026-11-13-1307`, D14 / D16 rejected; committed `review-agentcore-*` | `tests/evals/test_review_run.py`, `test_review_agentcore_run.py`, `test_review_recorded_run.py` | No |
| The AgentCore runtime is defined as code and deployed by the pipeline | Terraform `modules/agent_runtime` (AgentCore runtime V1, role, log group); deploy builds one arm64 image with `<sha>` and `<sha>-agent-runtime` tags, the apply moves the AgentCore runtime to the new image, rollback re-points it | `tests/test_workflows.py`, `tests/test_pipeline_scripts.py`, CI `terraform validate` | No |

## Flow

```mermaid
sequenceDiagram
    participant Q as SQS review queue
    participant W as review worker (ECS)
    participant DB as PostgreSQL
    participant R as AgentCore runtime (microVM per claim)
    participant B as Bedrock model + KB
    Q->>W: {"claim_id"}
    W->>DB: claim, possible duplicates, training claims
    W->>R: InvokeAgentRuntime (SigV4, session = claim id, payload)
    R->>B: model turns, Retrieve
    R-->>W: proposal | no_proposal | error, with token usage
    alt proposal
        W->>DB: proposal, claim → in_review
    else no_proposal
        W->>DB: claim → failed + reason
    else error or the call fails
        W-->>Q: message kept → redelivered; last delivery → failed + technical reason
    end
    W->>Q: delete message
```

## Design decisions

- **The worker passes the claim history in with the request:** before invoking, it runs
  `DatabaseClaimsHistory.find_possible_duplicates` and `list_training_claims` for the claim and
  sends both lists with it; in the AgentCore runtime a `PrefetchedHistory` (same `ClaimsHistory` protocol)
  answers the two tools from the payload, so the tools, their output and the `duplicate_of` check
  are unchanged. The duplicate query already ran on every claim (the prompt says to call
  `find_duplicate_claims` for every claim), so the only extra work is the training query, one
  indexed SELECT. The AgentCore runtime holds no database credentials and runs in `PUBLIC` network mode: an
  injected agent sees only this claim's matches. *Rejected:* the AgentCore runtime reads PostgreSQL (VPC mode
  in the private subnets, DB secret on the AgentCore runtime role, Bedrock through the NAT, a prompt-injected
  agent holding DB access, and it fails while the environment is stopped); training query only for
  `training` claims (a book extracted as `other` would lose the 5.1 yearly total: a wrong approve).
- **Worker → AgentCore runtime: IAM SigV4 with the review worker's task role.** The role gets
  `bedrock-agentcore:InvokeAgentRuntime` on this AgentCore runtime's ARN and its endpoints (`<arn>` and
  `<arn>/runtime-endpoint/*`), nothing else; boto3 signs with the task credentials, every call is in
  CloudTrail, no secret exists. No `authorizer_configuration` on the AgentCore runtime (SigV4 is the default)
  ([inbound auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html)).
  *Rejected:* JWT from a Cognito client-credentials app client (a client secret to store and
  rotate, token refresh, raw HTTPS since boto3 can't send a bearer token; built for end users
  calling an agent, not one service calling another).
- **One arm64 build for everything:** the AgentCore runtime needs an ARM64 container and takes only an image
  URI, no command ([container requirements](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html)).
  The deploy's image step runs on `ubuntu-24.04-arm` (native, free for public repositories); the
  Dockerfile gets a second target `agent-runtime` (same layers, `CMD` = the AgentCore runtime server on
  `0.0.0.0:8080`), pushed as `<sha>-agent-runtime` next to `<sha>`. ECS task definitions switch
  to `cpu_architecture = "ARM64"` (Fargate on Graviton, cheaper per vCPU-hour). *Rejected:* x86 app
  + a separate arm64 AgentCore runtime build (two architectures to keep working), multi-arch through QEMU
  (emulated `uv sync`, several times slower).
- **Platform version V1, set explicitly (`platform_version = "V1"`), one session per claim, idle
  timeout 60 s:** `runtimeSessionId` = the claim id (36 characters; the minimum is 33), so each
  claim runs in its own microVM, and a second delivery of the same claim reaches the same microVM.
  The agent is stateless between requests: everything it needs is in the payload. Idle timeout at
  the 60 s minimum (`lifecycle_configuration`) so memory stops billing a minute after the answer;
  `max_lifetime` stays 8 h. V1 starts the container fresh per session, so nothing is shared
  between claims. *Rejected:* V2 snapshot start (each session restores the same memory, so random
  state taken before the snapshot repeats in every session, including OpenSSL's, which TLS keys
  come from. Our Debian image's OpenSSL isn't the snapshot-safe build. Making it safe needs either
  an Amazon Linux 2023 base with `openssl-snapsafe-libs` and a distro Python 3.13, or creating every
  client after the restore and trusting no library to touch OpenSSL at import. V2 also has higher
  rates and a several-minute snapshot on every deploy
  ([V2](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-v2-optimize.html)));
  the default 15 min idle timeout (bills 15 min of idle memory per claim for nothing: requests are
  stateless).
- **`REVIEW_AGENT_RUNTIME_ARN` picks the agent:** set → the worker builds `AgentCoreClient`;
  unset → the in-process `StrandsReviewAgent` as today (local `make up`, tests). Both implement
  `ReviewAgent`, so `review_claim` and the worker loop don't change. Terraform always sets it on the
  deployed review worker. *Rejected:* AgentCore only (local stack would need AWS credentials and
  send local claims to the dev AgentCore runtime), a local AgentCore runtime container (a second client over plain
  HTTP to maintain).
- **The contract, `app/review/runtime_contract.py`** (Pydantic, JSON both ways):
  - request `{claim, possible_duplicates, training_claims}`: `ClaimUnderReview` as a model
    (expense, attendees, warnings, answered requests, `submitted_at`, `document_sha256`) and the
    two history lists as returned by `DatabaseClaimsHistory`;
  - response `{"outcome": "proposal", proposal, retrieved_clauses, model, usage}`,
    `{"outcome": "no_proposal", detail, usage}` or `{"outcome": "error", usage}` (a Bedrock, KB or
    tool failure after spending tokens), always HTTP 200 so the usage reaches the worker.
  The quote check runs in the AgentCore runtime (it needs the clauses retrieved there); the worker parses
  `ReviewProposal` without it and trusts the AgentCore runtime, which only it can call.
- **AgentCore runtime server, `app/review/runtime_app.py`:** a FastAPI app (already a dependency): `GET /ping`,
  `POST /invocations`, uvicorn on `0.0.0.0:8080`. Per request it builds `StrandsReviewAgent` with
  `PrefetchedHistory` from the payload; the model and KB clients are created once at startup.
  Settings: `ReviewRuntimeSettings`, a plain `BaseSettings` (not `Settings`: no database, Cognito
  or queues): `REVIEW_MODEL_ID`, `POLICY_KB_ID`, `AWS_REGION`, `REVIEW_MAX_TURNS`,
  `REVIEW_MAX_PROPOSAL_ATTEMPTS`, `LOG_LEVEL`. Logs go to stdout → the AgentCore runtime's CloudWatch log
  group, with the claim id in every line as today. *Rejected:* the `bedrock-agentcore` SDK app
  (a new dependency for two routes; its async-task ping states aren't needed).
- **Client, `app/review/agentcore.py`, `AgentCoreClient(arn, history: ClaimsHistory)`:**
  prefetches from the history it's given (the worker passes `DatabaseClaimsHistory`, the eval
  `RunHistory`), calls `invoke_agent_runtime` in `asyncio.to_thread` with `read_timeout` 900 s
  (the 15 min synchronous limit) and one attempt (SQS is the retry), and maps the response:
  `proposal` → `ValidProposal`, `no_proposal` → `NoValidProposal`, `error` →
  `BedrockRunError(usage)`. Any exception from the call (throttling, access denied, timeout, 5xx,
  an unparseable body) → `BedrockRunError(TokenUsage())`. `review_claim` then does what it does
  today: retry through SQS, `failed` with the technical reason on the last delivery, token metrics
  per claim.
- **AC2 is proven by one dev run through the AgentCore runtime, with a recheck:** `make eval-review
  args="--agentcore"` runs the 24 dev cases through `AgentCoreClient` (the ARN from
  `REVIEW_AGENT_RUNTIME_ARN` in `.env`; the flag, not the variable, picks AgentCore, so in-process runs
  stay in-process) with
  `RunHistory`. The results file records `agent_placement: "agentcore"` (not the ARN: the repository is
  public and the ARN holds the account id). Committed as `review-agentcore-<date>.json/.md`. Pass:
  every case except E02 (wrong in 2 of 3 T11 runs) has the decision it had in
  `review-2026-11-13-1307` (same prompt and model), D14 and D16 rejected. A case that differs gets
  2 more runs through the AgentCore runtime and 2 in-process (new `--ids D07,D17`: the named cases, each
  preceded by its `process_after` case, so D17 still finds D01); it fails AC2 only if it
  differs through the AgentCore runtime and not in-process. *Rejected:* dev + holdout (twice the cost; the
  holdout set exists to judge prompt changes, and this changes no prompt), three full runs (3× the
  cost for a transport change).
- **The AgentCore runtime is part of the release and rolls back with it.** Terraform sets
  `container_uri = <repo>:<sha>-agent-runtime`, so the apply creates a new AgentCore runtime version and
  `DEFAULT` follows it. "record the live release" also saves the AgentCore runtime's current configuration
  (`get-agent-runtime`; skipped on the first deploy, when there is none). On any failure after the
  record, the migration included, "roll back the AgentCore runtime" runs
  `infra/scripts/rollback-agent-runtime.sh`: `update-agent-runtime` with the saved image, role,
  network, lifecycle and environment (the update replaces the whole configuration) and waits for
  `READY`, so the AgentCore runtime never stays a release ahead of the workers. After a successful migration,
  "roll back" then restores ECS and the frontend as today. Terraform state
  shows the new image until the next apply, which sets it again. The old worker still calls the new
  AgentCore runtime between the apply and the ECS deploy, so a contract change keeps accepting the previous
  request shape for one release (a unit test sends a saved request). *Rejected:* no AgentCore runtime rollback
  (agent and worker from different releases after a failed deploy), an endpoint per release with the
  name in the worker's task definition (endpoint cleanup, 10 per AgentCore runtime, the most pipeline work).

## Questions

- **What does the AgentCore runtime give you that the worker did not, and what does it cost per claim?**
  *Gives:* the agent is deployed and versioned on its own (immutable AgentCore runtime versions, `DEFAULT`
  endpoint) and scales per claim: each claim gets its own microVM, up to 2,500 active sessions and
  25 new sessions/s per account in eu-north-1 by default
  ([quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)).
  Isolation: the microVM ends and its memory is wiped after the claim; the AgentCore runtime role reaches only
  the model and the KB, so a prompt-injected run has no database, queue or other claims. *Doesn't
  give, today:* more throughput. The worker still takes one message at a time
  (`MaxNumberOfMessages=1`) and waits for the answer; the AgentCore runtime's scale is used only once the
  worker reviews concurrently or runs more tasks. The worker's Fargate task stays. Costs that come
  with it: a network hop, a second IAM role and log group, an arm64-only build.
  *Cost per claim:* CPU is billed only while active (waiting for Bedrock is free), memory per second
  from microVM start until the 60 s idle timeout ends it, 1 s and 128 MB minimums; V1 rates
  $0.0895 per vCPU-hour and $0.00945 per GB-hour
  ([pricing](https://aws.amazon.com/bedrock/agentcore/pricing/), not labelled by region). Estimate
  for one review: ~5 vCPU-seconds (≈ $0.0001) + ~0.3 GB for ~2 min (≈ $0.0001), so about **$0.0002
  per claim**, under 1 % of the claim's Bedrock tokens (tens of thousands of input tokens with
  Sonnet 4.6, cents per claim). Moving all tasks to Graviton lowers the Fargate bill by about 20 %.
  Measured values from `CPUUsed-vCPUHours` / `MemoryUsed-GBHours` for the manual run go in Results.
- **How long does the first call after an idle period take, and does that matter for this flow?**
  With one session per claim, *every* claim is a first call: V1 starts a fresh microVM and our
  container (image pull, then Python importing Strands, boto3 and FastAPI before `/ping` passes).
  AWS publishes no figure for V1; we expect seconds, measured in the manual run as the time to the
  first byte of a new session minus the same request repeated within 60 s, and recorded in Results.
  It doesn't matter here: reviews are asynchronous through SQS, a review already spends tens of
  seconds on model turns, and the employee sees `in_review` later anyway. It would matter only if
  start-up plus the run passed the 300 s visibility timeout (see Known gaps).

## Configuration

- **Settings:** worker `REVIEW_AGENT_RUNTIME_ARN` (optional, `ReviewWorkerSettings`; empty in
  `.env.example` so local runs stay in-process). AgentCore runtime: `ReviewRuntimeSettings` reads
  `REVIEW_MODEL_ID`, `POLICY_KB_ID`, `AWS_REGION`, `REVIEW_MAX_TURNS`,
  `REVIEW_MAX_PROPOSAL_ATTEMPTS`, `LOG_LEVEL`, set by Terraform `environment_variables` (4 KB limit).
- **Terraform `modules/agent_runtime`:** `aws_bedrockagentcore_agent_runtime` named
  `<project>_review` (names allow no hyphens), `platform_version = "V1"`, `network_mode = "PUBLIC"`,
  `protocol_configuration` HTTP, `lifecycle_configuration` idle 60 s / max 28,800 s, container
  `<repo>:<image_tag>-agent-runtime`; execution role `<project>-review-agent-runtime` under the
  environment's IAM path with the boundary, trusted by `bedrock-agentcore.amazonaws.com` with
  `aws:SourceAccount` and `aws:SourceArn` conditions, allowed ECR pull, logs, `bedrock:InvokeModel`
  on the inference profile, `bedrock:Retrieve` on the clause KB; log group
  `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT`, 14 days. Not gated by `runtime_enabled` (nothing
  bills while idle). Outputs `runtime_arn`, `runtime_id`, `log_group_name`; the environments output
  them as `agent_runtime` for the pipeline.
- **`modules/review`:** the worker policy loses `InvokeModel` / `Retrieve` and gains
  `bedrock-agentcore:InvokeAgentRuntime` on the AgentCore runtime and `<arn>/runtime-endpoint/*`.
  **`modules/runtime`:** `cpu_architecture = "ARM64"`; `REVIEW_AGENT_RUNTIME_ARN` in the review
  worker's environment.
- **`bootstrap`** (an admin applies it once before the first T16 deploy): deploy role
  `bedrock-agentcore:*` in the region, `iam:PassRole` to `bedrock-agentcore.amazonaws.com`,
  `iam:CreateServiceLinkedRole` for `runtime-identity.bedrock-agentcore.amazonaws.com` (AgentCore
  creates that role with the account's first AgentCore runtime), and
  `logs:*` on `/aws/bedrock-agentcore/runtimes/<project>_*` (the AgentCore runtime's log group; AgentCore runtime names
  turn the prefix's hyphens into underscores); boundary adds `bedrock-agentcore:InvokeAgentRuntime`, `logs:DescribeLogGroups`,
  `logs:DescribeLogStreams`.
- **Pipeline:** the deploy job runs on `ubuntu-24.04-arm`; `push-image.sh` builds the targets `app`
  (`<sha>`) and `agent-runtime` (`<sha>-agent-runtime`); "record the live release" saves the
  AgentCore runtime configuration; "roll back the AgentCore runtime" runs `infra/scripts/rollback-agent-runtime.sh`
  on any failure after the record (the migration's too), before "roll back".
  Dockerfile stages `build` → `base` → `agent-runtime` (uvicorn `app.review.runtime_app:app`, port
  8080) and `app` (last, so `docker build` and compose still give the API). `docs/pipeline.md`
  describes the new steps.
- **Code:** `app/review/runtime_contract.py`, `runtime_app.py`, `agentcore.py`, `PrefetchedHistory`
  in `claims_history.py`, `--agentcore` in `evals/review`; `uv add --dev
  "boto3-stubs[bedrock-agentcore]"` (the existing extras list).

## Known gaps

- Throughput is unchanged: one claim at a time per worker task, one task. Concurrent receives or
  more tasks (T09 "Scaling") are what use the AgentCore runtime's scale.
- The agent's own limits (12 turns × 120 s model timeout) can exceed the 15 min synchronous call
  limit (the call fails and counts as a delivery) and the 300 s visibility timeout (the claim is
  delivered again while running; same session id, so the second run lands on the same microVM; the
  row lock still keeps one proposal).
- After a rollback, Terraform state shows the new AgentCore runtime image until the next apply sets it again.
  A contract change must stay compatible for one release.
- The smoke request doesn't call the agent: a broken agent passes the deploy and shows up as
  `failed` claims and the `ClaimsFailed` alarm; the fix is `git revert`.
- The pricing page's rates aren't labelled by region; eu-north-1 may differ slightly.
- The review worker keeps 0.5 vCPU / 1 GB although the agent no longer runs in it.
- AgentCore Observability (traces) isn't enabled: logs and the T14 token metrics only.
- On an environment never deployed before, the first deploy fails at the AgentCore runtime: its image is
  pushed only after the apply creates the ECR repository. Running the deploy again pushes the image
  first and creates the AgentCore runtime.

## Testing

- **Unit:** the contract (round trip; a saved request from the previous release still parses);
  `AgentCoreClient` with a botocore `Stubber` (payload with claim and both history lists,
  session id = claim id, each outcome mapped, call errors and unparseable bodies →
  `BedrockRunError`, usage carried); `runtime_app` through FastAPI's test client with the scripted
  `Model` fake (`/ping`; `/invocations` returning proposal, no_proposal and error; tools answering
  from `PrefetchedHistory`; the quote check still applied); worker picks the agent from the setting;
  eval `--agentcore`, `--ids` with `process_after`, and the committed AgentCore run against the
  baseline; workflows (arm runner,
  both tags, record and rollback steps, docs entries) and `rollback-agent-runtime.sh` against the
  fake `aws`.
- **Integration:** `test_review_db.py` drives the worker with a stubbed AgentCore runtime client: proposal →
  `in_review` with the proposal stored, no_proposal → `failed` with the reason, error on the last
  delivery → `failed` with the technical reason.
- **Manual:** admin applies `bootstrap`; deploy to dev from the temporary deploy branch (T14
  procedure), Start; D01 through the UI ends `in_review` with a proposal, E10 ends `failed`; the
  AgentCore runtime log group shows the claim; time a new session vs a repeat within 60 s; read the AgentCore runtime's
  CPU and memory metrics for the cost; `make eval-review args="--agentcore"`; a deploy with a
  broken smoke request restores the AgentCore runtime's previous image along with ECS and the frontend.

## Results

2026-11-26/27, on `dev`, deployed from the temporary branch mapped to the `dev` environment. The
first deploys found three gaps, now fixed: `terraform fmt`; the deploy role couldn't create the
`AWSServiceRoleForBedrockAgentCoreRuntimeIdentity` service-linked role AgentCore creates with an
account's first AgentCore runtime; and the AgentCore runtime's role created its own log group
before Terraform could (it no longer has `logs:CreateLogGroup`; the apply that removed it still
raced once, because the change hadn't propagated: CloudTrail shows the role creating the group 2 s
before Terraform).

D02 through the UI: the worker sent the claim and its prefetched history, the agent ran in the
AgentCore runtime (duplicate check, three KB searches, `get_clause`, ~10 s) and the worker stored a
reject citing 1.2, 2.1 and 7.1; the claim ended `in_review`. E10 ended `failed` at extraction, as
before. A new session took 12.2 s, the same request repeated within 60 s 11.0 s: about 1 s of
start-up next to ~10 s of model turns.

33 invocations (D02, the two timing calls, 24 eval cases, three rechecks of two cases): average
latency 15.5 s, 0.0935 vCPU-hours and 1.654 GB-hours in total, so 10 vCPU-seconds and 180
GB-seconds per claim, **≈ $0.0007 per claim** at the V1 rates, two thirds of it memory (billed until
the 60 s idle timeout). That is 3–4× the estimate above, still under 1 % of a review's Bedrock tokens.

`review-agentcore-2026-11-26-1659`: 21/24, D14 and D16 rejected. Against `review-2026-11-13-1307`,
D13 (reject, clause 4.1) and E05 (needs_info, attendees) differed besides E02. Rechecks through the
AgentCore runtime (`review-agentcore-2026-11-27-0821`, `-0823`, and one run overwritten by the
second in the same minute): D13 approve 3 of 3, E05 approve 2 of 3, so both were model variance and
no in-process rerun was needed; AC2 met.

A deploy with a broken smoke request put the AgentCore runtime back on its previous image, but the
services stayed: each apply had deregistered the replaced task definition revisions, and ECS
refuses an INACTIVE one (a T14 gap; T14 never ran this test). `skip_destroy` now keeps them ACTIVE;
after one clean deploy, a second broken one restored the AgentCore runtime, the API, both workers
and the frontend.

## Commit plan

- [x] 1. Contract and prefetched history: `runtime_contract.py` (request, three responses), `PrefetchedHistory`, `ReviewRuntimeSettings`, `boto3-stubs[bedrock-agentcore]` — AC1 — `add the agent runtime contract, prefetched claim history and runtime settings`
- [x] 2. AgentCore runtime server: `runtime_app.py` (`/ping`, `/invocations` building `StrandsReviewAgent` with `PrefetchedHistory`), Dockerfile stages `base` → `agent-runtime` / `app` — AC1 — `add the agent runtime server with ping and invocations, agent-runtime docker target`
- [x] 3. Client and worker: `AgentCoreClient` (prefetch, SigV4 call in a thread, outcome mapping), `REVIEW_AGENT_RUNTIME_ARN` picks the agent in `run_worker`, `.env.example`, integration through the worker with a stubbed AgentCore runtime — AC1 — `add the agentcore client, pick it in the review worker from REVIEW_AGENT_RUNTIME_ARN`
- [x] 4. Eval through the AgentCore runtime: `--agentcore` (ARN from `REVIEW_AGENT_RUNTIME_ARN`), `--ids` with `process_after` cases, `agent_placement` in the results file — AC2 — `add --agentcore and --ids to the review evaluation, the agent placement in its results`
- [x] 5. Terraform: `modules/agent_runtime` (AgentCore runtime V1, role, log group), review worker policy → `InvokeAgentRuntime`, ECS tasks ARM64, `REVIEW_AGENT_RUNTIME_ARN` on the worker, dev and prod wiring, bootstrap deploy role and boundary — AC3 — `add the agent runtime terraform module, invoke permission for the review worker, arm64 tasks, bootstrap agentcore permissions`
- [x] 6. Pipeline: arm runner, `push-image.sh` builds both targets, "record the live release" saves the AgentCore runtime configuration, `rollback-agent-runtime.sh` in the rollback step, `docs/pipeline.md` — AC3 — `add the agent runtime image to the deploy with its record and rollback, arm runner, pipeline docs`
- [x] 7. Committed AgentCore run (after the developer deploys dev and runs `make eval-review args="--agentcore"`): `review-agentcore-*.json/.md`, `test_review_agentcore_run.py`, Results — AC2 — `add the agentcore review evaluation run and its comparison with the in-process run`
