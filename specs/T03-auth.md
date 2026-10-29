# T03 — Authentication and roles

**Goal:** only the right people see and decide claims. **Out of scope:** login UI (T13), MFA.

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| Users sign up with email verification | Cognito user pool: email as username, `auto_verified_attributes = ["email"]`, self sign-up | Manual smoke test; `terraform validate` in CI |
| Every new user is an EMPLOYEE | Post-Confirmation Lambda adds the user to the `employee` group | `tests/lambdas/`: sign-up confirmation → `AdminAddUserToGroup(employee)`; password-reset confirmation → no call |
| Only an administrator can make someone a REVIEWER | `PUT /users/{sub}/role` guarded by `require_roles(Role.ADMIN)`; API assigns `employee` / `reviewer` only | `tests/users/`: admin → 200; employee / reviewer → 403; target `admin` → 422 |
| Users cannot change their own role | Group membership changes only through Cognito admin APIs (IAM), never by the user; the endpoint refuses `actor.sub == target` (admins too) | `tests/users/`: self change → 403 |
| `GET /me` returns identity and role; missing/invalid token → 401 | `get_current_user` dependency verifies the access token | `tests/users/`: no header, non-Bearer header, garbage or revoked token → 401; `tests/auth/test_tokens.py`: each invalid-token case rejected |
| A wrong role gets 403 | `require_roles(*roles)` dependency factory | `tests/users/`: employee / reviewer on the admin endpoint → 403, admin passes; no role group → 403 |
| User pool defined in infrastructure as code | Terraform in `infra/terraform/` (`environments/dev` calling `modules/{cognito,iam,lambda}`), S3 backend | CI `terraform fmt -check` + `validate` |

## Design decisions

**Terraform** for all AWS resources from here on. State lives in an S3 bucket (created once by hand)
with S3-native locking (`use_lockfile`); `backend.hcl` holds the bucket name locally, like `.env`.
*Rejected: SAM* (Lambda/API-centric, weak for RDS/ECS/Cognito), *CDK* (adds a synth step on top of
CloudFormation).

**Roles are Cognito user groups**: `admin`, `employee` and `reviewer`, defined in Terraform. Cognito
puts the caller's groups in the access token (`cognito:groups`), so the API reads the role from the
token it already verifies, with no DB lookup. Only IAM-authorized admin APIs can change membership,
so a user has no way to edit their own role. *Rejected: a `roles` lookup table in PostgreSQL*. It needs
more code (tables, trigger, seed, provisioning) for what Cognito provides natively.
*Rejected: a `custom:role` attribute*, because a writable attribute is a self-promotion risk.

**One role per user.** Group precedence is admin=1, reviewer=2, employee=3. If a user is in several
groups, the most privileged one wins. The role endpoint keeps exactly one group: it removes the others
and adds the target.

**New users join `employee` through a Post-Confirmation Lambda**, so every token carries an explicit
group. It runs only for `PostConfirmation_ConfirmSignUp`, not for a confirmed password reset. A token
with no known group gets 403 (fail closed).
*Rejected: treating "no group" as employee*, because it leaves the default role implicit.

**First admin:** was added with `aws cognito-idp admin-add-user-to-group --group-name admin`.
The API assigns `employee` and `reviewer` only.

**Role checks are FastAPI dependencies:** `require_roles(Role.ADMIN)` is used in `dependencies=[...]` or
as an `Annotated` parameter.

**Cognito calls are behind a `UserDirectory` protocol** (GetUser for `/me`'s email, group changes).
boto3 is blocking, so each call runs in `asyncio.to_thread`. Tests inject a fake.

## Which token does the API accept, and which claims does it verify?

- **The access token.** It is the token Cognito issues for calling resource servers. The ID token
  describes the user to the client app and can't be revoked with `GlobalSignOut`.
- Verified on every request, offline, against the pool's JWKS (keys cached):
  - **signature**: RS256 only, key selected by `kid`. Other algorithms, including `none` and HS256,
    are refused.
  - **`iss`** = `https://cognito-idp.<region>.amazonaws.com/<pool_id>`
  - **`token_use`** = `access`, which rejects ID tokens
  - **`client_id`** = our app client. Access tokens have no `aud`, and this claim plays that role.
  - **`exp`** and **`iat`**: required, with a small clock leeway
  - **`sub`**: required. It is the user's identity.
  - **`cognito:groups`**: read, not required. Missing or unknown groups → no role → 403.
- Any failure → 401 with `WWW-Authenticate: Bearer`. The reason is logged, never returned.

## How do tests obtain tokens without calling Cognito?

- A test RSA keypair is generated per session. `make_token(**claims)` signs JWTs with it using a test
  `kid`, with `cognito:groups` set as each test needs. A `TokenVerifier` that reads the test public key
  from memory replaces the real one through `dependency_overrides`. The verification code under test
  is the real one; only the key source differs.
- `UserDirectory` is replaced by an in-memory fake. The Lambda handler is tested with a stubbed boto3
  client.
- No test reaches AWS.

## Known limitations

- In a situation of admin promoting or demoting a signed in user's role, the user won't see the change until the tokens are refreshed, could add a force refetch on window focus into /me call to get the latest role state on frontend later.
- An admin can't demote themselves; another admin or the CLI has to do it.

## Test plan

- Unit (no DB, no AWS):
  - Verifier rejects: expired, wrong `iss`, `token_use=id`, wrong `client_id`, unknown `kid`, HS256 /
    `none`, bad signature, missing `sub`.
  - Missing or malformed `Authorization` → 401.
  - No role group → 403.
  - `require_roles` → 403 / pass.
  - Picking the role from groups by precedence.
  - Role endpoint: admin succeeds; non-admin, self-change, `admin` as target, unknown user.
  - Lambda: sign-up adds to `employee`, password reset is ignored.
  - Settings derive the issuer and JWKS URL.
- Coverage ≥ 80% enforced in CI.
