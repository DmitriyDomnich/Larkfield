# T13 — Frontend

**Goal:** the flow can be used and demonstrated without an API client. **Out of scope:** admin
pages, dashboards, editing `corrected_fields` in the UI, hosting (the frontend runs locally like the
API; S3 + CloudFront later), a new document in answer to `needs_info` (T12).

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| Login through Cognito; pages limited by role | `<AuthGate>` shows Amplify's `<Authenticator>` until signed in. The role comes from `GET /me`, never from decoding the token. One page → roles map (`pageAccess.ts`): employee → `/claims*`, reviewer → `/claims*` and `/review*`. The nav shows only the pages the role may open; `<PageGate>` around every page redirects to `/` at once when a page is opened by URL without access. `/` redirects by role; admin → an "administrator pages are coming soon" notice with sign-out. An unknown URL shows a "Page not found" page (`out/404.html`) with a link to `/`. Signing out clears the query cache. The API still enforces every rule; the map is navigation only | `src/features/auth/AuthGate.test.tsx`: signed out → Authenticator, signed in → app, sign-out clears the cache. `PageGate.test.tsx`: each role × each page. `HomeRedirect.test.tsx`: redirect by role, admin notice. `NotFoundNotice.test.tsx`. `AppShell.test.tsx`: nav links per role |
| Employee: create a claim and upload its file; list of own claims with status | `/claims/new`: purpose, attendees, pre-approval ref, file (type and size checked before sending, to mirror T04) → `POST /claims` → `uploadToS3` posts the form fields then the file to `upload.url` → `/claims/view?id=`, which polls until `extracted`/`failed`. `/claims`: `GET /claims`, newest first, status badge, failure reason, 20 per page. `/claims/view`: status, file link, failure reason, the reviewer's comments from `/review`, and an answer form when `needs_info` (a message, plus the attendees and pre-approval reference to correct) → `POST /claims/{id}/answer` | `NewClaimForm.test.tsx`: validation, the S3 form's field order (file last), S3 failure → error and no redirect. `ClaimList.test.tsx`: rows, statuses, paging. `ClaimDetail.test.tsx`: polling stops at a waiting status. `AnswerForm.test.tsx`: shown only for `needs_info`, posts the body, 409 message |
| Reviewer: claims in review; one page with the document, its extracted fields and warnings, and the proposal with its quoted clauses; approve, reject or request information with a comment | `/review`: `GET /claims?status=in_review`. `/review/claim?id=` has 4 panels, each with its own query: the claim, `DocumentViewer` (`GET /file`: PDF in an `<iframe>`, image in an `<img>`), `ExtractionPanel` (new `GET /claims/{id}/extraction`: fields, line items, warnings highlighted), `ProposalPanel` (the newest round of `GET /review`: decision, each reason's clause id, quote and explanation, missing information, duplicate link; earlier rounds collapsed). `DecisionForm`: approve / reject / needs_info, preset to the proposal; the comment is required for `reject` and `needs_info`, and when the decision differs from the proposal (the same rule as the API, and a 422 from the server is shown); 409 → "already decided" and a refetch; hidden on the reviewer's own claim | `ReviewQueue.test.tsx`, `ReviewClaim.test.tsx` (all panels render from API data, own-claim notice), `ProposalPanel.test.tsx` (quotes rendered as text), `DecisionForm.test.tsx` (comment rule, body, 409/422). `tests/review/test_decisions_db.py` (reject as proposed without a comment → 422). `tests/extraction/test_extraction_api.py`, `test_extraction_api_db.py` |
| Loading and error states on every async view | Every query renders through `<QueryState>`: a spinner while loading, an error with "Try again" (refetch) on failure, the API's `detail` for 4xx, and a generic message for 5xx/network. A 401 signs out. A mutation disables its button while pending and shows its error inline. One panel failing doesn't blank the review page | `QueryState.test.tsx`. Each async view's test has a loading case and an error case (MSW returns 500) |
| A change in an API response shape is caught by the build or tests, not by a user | Types are generated from the committed `frontend/openapi.json` (see Design decisions). MSW handlers are typed by the same schema (`openapi-msw`), so a test fixture of the old shape fails `tsc` | `tests/test_openapi_snapshot.py`. CI `frontend` job: `gen:api` + `git diff --exit-code`, `tsc --noEmit`, `next build` |

## Flow

```
open app → Amplify session? no → <Authenticator> (SRP sign-in / sign-up + email code)
         → GET /me → role → / redirects: employee → /claims, reviewer → /review, admin → notice
employee  /claims/new → POST /claims → POST S3 form (204) → /claims/view?id=
          poll GET /claims/{id} every 3 s: pending_upload → uploaded → extracting → extracted → in_review
          S3 refuses → error shown; the claim stays pending_upload (T04 gap), submit again
          needs_info → AnswerForm → POST /answer → extracted → polling again
reviewer  /review → GET /claims?status=in_review → /review/claim?id=
          GET claim, /file, /extraction, /review in parallel → DecisionForm → POST /decision (201)
          → back to /review; 409 → "already decided", refetch; own claim → no form
every request: fetchAuthSession() (Amplify refreshes) → Authorization: Bearer <access token>
          401 → signOut() → <Authenticator>
```

## Design decisions

- **Static export SPA:** Next.js App Router with `output: 'export'`, every page a client component
  that fetches with the user's access token. Each page shows one user's data behind a token, so
  request-time rendering or a server cache would only ever serve a layout and a spinner. Nothing to
  run but static files. Costs: no `[id]` routes (`generateStaticParams` can't know claim ids), so
  details are `?id=` pages. No `headers()`, so the CSP goes in a `<meta>` tag
  (https://nextjs.org/docs/app/guides/static-exports). *Rejected:* `next start` with browser-side
  data (a Node process to run and host, for prettier URLs only). A Next server as BFF holding
  tokens in an httpOnly cookie (a second backend; an injected script can still call the proxy).
- **Login with Amplify's `<Authenticator>`** (`aws-amplify`, `@aws-amplify/ui-react`) against the
  existing public app client. It signs in with SRP, so the password never leaves the browser
  (https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html).
  It also gives sign-up with the email code and forgot password, with no Terraform change. Our
  tests cover the wrapper (signed out → Authenticator; signed in → app), not Amplify's forms.
  *Rejected:* our own forms on `aws-amplify/auth` (3-4 forms, and every Cognito challenge and
  error handled by us). Hosted UI + PKCE (a Cognito domain and callback URLs in Terraform, and
  login leaves the app).
- **API types are generated from a committed `frontend/openapi.json`:** `make openapi` runs
  `python -m app.openapi` (it prints `create_app().openapi()`), writes the output to that file, then
  runs `openapi-typescript`, which writes `frontend/src/api/schema.d.ts`. Every call goes through
  one `openapi-fetch` client, so paths, params, bodies and responses are typed. Money (`Decimal`)
  arrives as a string and is shown as-is, never parsed to a float. The chain that catches a shape
  change: `tests/test_openapi_snapshot.py` fails until the file is regenerated. CI regenerates
  `schema.d.ts` and runs `git diff --exit-code`. `tsc --noEmit` then fails at every use of a removed
  or retyped field. *Rejected:* runtime zod from a generator (hey-api/orval). It also catches a
  server deployed out of step with the bundle, but it is a heavier toolchain, and API and frontend
  ship from one repo. Hand-written types (nothing links them to the API).
- **New `GET /claims/{id}/extraction`** (`app/extraction/router.py`, registered in `create_app`),
  for the owner and reviewers. `service.get_extraction` finds the claim through
  `claims.service.get_claim`, which is already scoped (another employee's claim gets the same 404
  as a missing one), then loads the `Extraction` by `document_id` with
  `selectinload(Extraction.line_items)`. It returns `ExtractionRead`: the `ExtractedExpense` fields,
  `warnings: list[ExpenseWarning]`, `ai_model` and `created_at`. The answers are 404
  `Claim not found` and 404 `The claim has no extraction yet`. Summary, `response_model` and
  `ErrorDetail` responses as in T04. *Rejected:* reviewers only (owners could never see what the
  model read from their receipt). Embedding it in `ClaimRead` (every list query would load
  extractions and line items, and T04's shared schema would change).
- **Employee detail page with the `needs_info` answer:** the whole loop can be shown in the UI,
  using T12's endpoints. *Rejected:* a read-only detail page (the answer would need curl, against
  the goal). The list alone (the employee couldn't see why a claim was rejected or what information
  is needed).
- **By feature, thin routes:** route files only render one feature component (access is checked once,
  by `PageGate` in `AppShell`), like the backend's thin routers. Every component has its own folder
  holding the component and its `*.test.tsx` (`QueryState/QueryState.tsx`, `QueryState/QueryState.test.tsx`).
  ```
  frontend/  openapi.json, .env.example, next.config.ts, package.json
    src/app/          routes only: layout.tsx, page.tsx (/ → by role), not-found.tsx, claims/, claims/new/, claims/view/, review/, review/claim/
    src/core/         config.ts (NEXT_PUBLIC_* values), providers.tsx (TanStack Query), csp.ts
    src/api/          schema.d.ts (generated), types.ts (schema aliases), client.ts (openapi-fetch +
                      Bearer), errors.ts, queryClient.ts
    src/features/auth/    AuthGate/, PageGate/, HomeRedirect/, hooks/useMe.ts, pageAccess.ts, amplifyConfig.ts
    src/features/claims/  ClaimList/, NewClaimForm/, ClaimDetail/, AnswerForm/, AttendeesFields/,
                          ClaimFileLink/, ReviewerComments/, hooks/ (queries + mutations),
                          uploadToS3.ts, claimFormRules.ts
    src/features/review/  ReviewQueue/, ReviewClaim/, DocumentViewer/, ExtractionPanel/, ProposalPanel/,
                          DecisionForm/, hooks/ (useExtraction, useDecideClaim), decisionLabels.ts
    src/components/widgets/  shared by pages: QueryState/, LoadingSpinner/, StatusBadge/, Pager/,
                             FormError/, LinkRow/ (clickable table row), BackLink/, LogoMark/,
                             AppShell/ (nav by role), NotFoundNotice/
    src/components/ui/  shadcn/ui components (generated)
  ```
  *Rejected:* by type (`components/`, `hooks/`): a feature's pieces end up scattered and route
  files grow.
- **A comment is required to reject (changes T12's rule):** T12 asked for a comment only when the
  decision differs from the proposal or is `needs_info`. Employees never see the agent's proposal
  (`GET /review` hides it), so a rejection that agrees with the proposal reached them with no
  reason. `decide_claim` now also requires a comment for `reject`; the form mirrors it.
- **Server state in TanStack Query.** The detail pages poll `GET /claims/{id}` every 3 s while the
  status is `pending_upload`, `uploaded`, `extracting` or `extracted`. Polling stops at `in_review`
  and `needs_info` (they wait for a person) and at `approved`, `rejected` and `failed`. Lists
  refetch on window focus. This also picks up a role change on the next `/me` (T03 gap). The
  presigned file link is valid for 5 minutes, so it is cached for 4. A "Reload document" button
  fetches a new one.
- **The API allows the frontend's origin:** `CORSMiddleware` in `create_app` with
  `allow_origins=settings.frontend_origins`, methods `GET` and `POST`, headers
  `Authorization` and `Content-Type`, no credentials (the token is a header, not a cookie). The
  bucket's CORS already lists `frontend_origins` (T04, default `http://localhost:3000`).
- **UI: shadcn/ui on Tailwind CSS** (https://ui.shadcn.com/docs/installation/next). Accessible
  Radix-based components are copied into `src/components/ui/` by the shadcn CLI: Button, Table,
  Badge, Input, Textarea, RadioGroup, Label, Alert, Skeleton, Card, Collapsible. They are generated
  code, kept as generated, with our components built on them. Amplify's `<Authenticator>` keeps its
  own stylesheet, themed through its CSS variables to match. *Rejected:* Mantine (its own styling
  system next to Tailwind, a larger bundle). MUI (the heaviest bundle, and Emotion injects styles at
  runtime). Tailwind only (focus handling, radio groups and collapsibles left to us).
- **Plain stack choices:** npm, Vitest + React Testing Library + MSW. Amplify is
  mocked with `vi.mock("aws-amplify/auth")`. ESLint `next/core-web-vitals` with `react/no-danger`
  as an error.

## Questions

- **Where does the browser keep tokens?** In `localStorage`, Amplify's default
  (https://docs.amplify.aws/react/build-a-backend/auth/concepts/tokens-and-credentials/): the access
  and ID tokens (15 min) and the refresh token. They survive reloads and are shared across tabs. The
  refresh token's lifetime drops from 30 days to **8 hours** (`refresh_token_validity` in
  `modules/cognito`), so a forgotten session ends within a working day. Sign-out calls
  `signOut()`, which revokes the refresh token (the client has `enable_token_revocation`) and clears
  storage. *Rejected:* `sessionStorage`. Its copy goes when the tab closes, but a token that was
  already copied stays valid just the same, and every new tab asks for a login. In-memory: a login on
  every reload, and `fetchAuthSession()` still hands the tokens to any script.
- **What could a script injected into the page do with them?** Everything the user can do, from
  anywhere, for a while. Any script running in our origin can read `localStorage` or call
  `fetchAuthSession()`. With the tokens it can call the API as that user: an employee's claims and
  their files, or, for a reviewer, every claim and file plus decisions on them. Sending the refresh
  token elsewhere gives it fresh access tokens for up to 8 hours, or until the user signs out. Even
  after a sign-out, an access token it already holds works for up to 15 minutes, because the API
  checks tokens offline (T03). Only `/me` asks Cognito. No storage choice prevents this, so the
  defence is keeping scripts out:
  - React escapes all text. Every user- and model-written string (purpose, comments, the agent's
    quotes and explanations, filenames) renders as text. No `dangerouslySetInnerHTML` (ESLint
    `react/no-danger` as an error), no markdown/HTML rendering, no third-party script tags or CDNs.
  - A `<meta>` CSP: `default-src 'self'`, `script-src 'self' 'unsafe-inline'`, `style-src 'self'
    'unsafe-inline'` (Radix and Amplify UI set inline `style` attributes), `connect-src` limited
    to the API, Cognito (`cognito-idp.<region>.amazonaws.com`) and the documents bucket,
    `img-src`/`frame-src` limited to `'self'` and the bucket, `object-src 'none'`, `base-uri 'self'`,
    `form-action 'self'`. A foreign script origin is refused, and `fetch` to an unknown host fails.
    Limits: `'unsafe-inline'` lets an injected inline script run (the static export's own inline
    hydration scripts need it, and nonces need a server,
    https://nextjs.org/docs/app/guides/content-security-policy). A top-level navigation to
    `https://evil/?t=…` still leaks a token, and `frame-ancestors` is ignored in `<meta>`.

## Configuration

- **API:** `FRONTEND_ORIGINS` on `Settings` (`list[str]`, default `[]`, so no CORS for the workers),
  added to `.env.example` and to the compose `api` service.
- **Frontend `frontend/.env.example`:** `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_COGNITO_REGION`,
  `NEXT_PUBLIC_COGNITO_USER_POOL_ID`, `NEXT_PUBLIC_COGNITO_APP_CLIENT_ID`,
  `NEXT_PUBLIC_DOCUMENTS_ORIGIN` (the bucket's regional URL, for the CSP). They are baked in at
  build time and are public values (a public client), not secrets. The build fails if any is
  missing.
- **Terraform `modules/cognito`:** `refresh_token_validity = 8`, `token_validity_units.refresh_token
  = "hours"`. You run `terraform apply`.
- **Make / CI:** `make openapi` (dump + `npm --prefix frontend run gen:api`). New CI job `frontend`
  (Node 22, `npm ci`): lint, `tsc --noEmit`, `vitest run`, `gen:api` + `git diff --exit-code`,
  `next build` (with placeholder env). `README.md` gets a "Run the frontend" section.

## Known gaps

- `'unsafe-inline'` in `script-src`, and no `frame-ancestors` (clickjacking) until hosting sets real
  response headers. A post-build hash step could remove `'unsafe-inline'`.
- An access token stolen before sign-out still works for up to 15 minutes (offline verification).
- If the browser closes between `POST /claims` and the S3 upload, the claim stays `pending_upload`
  in the list (T04). The employee submits again.
- The bundle and the API are not versioned together. A deployed API ahead of a cached bundle would
  surface as runtime errors (no runtime validation). This matters only once hosted.
- The review queue polls nothing. Another reviewer's decision shows on focus or as a 409.

## Testing

- **Unit (frontend, Vitest + RTL + MSW, no AWS):** every component listed under Acceptance
  criteria, plus a loading and an error case per async view, the page gate, `uploadToS3`'s field
  order, and the decision comment rule.
- **Unit (API):** `tests/extraction/test_extraction_api.py` (401, admin 403, OpenAPI documents the
  route); `tests/test_openapi_snapshot.py`; `tests/test_cors.py` (a preflight from an allowed origin
  gets `Access-Control-Allow-Origin`, another origin doesn't).
- **Integration (`@pytest.mark.integration`):** `tests/extraction/test_extraction_api_db.py`: owner
  and reviewer 200 with line items and warnings, another employee and a random id get the same 404,
  a claim not yet extracted → 404 `The claim has no extraction yet`.
- **Manual:** with `make up`, the workers, and `npm run dev`: sign up a new user (gets the email
  code) as employee and submit a PDF, watching it reach `in_review`. As a reviewer, open it, check
  the document, fields, a warning and the quotes, and choose needs_info with a comment. As the
  employee, answer, and the claim is reviewed again. As the reviewer, approve. The employee sees
  `approved`. Then: an admin sees the "coming soon" notice; an employee opening `/review` by URL
  lands on `/claims`; an unknown URL shows "Page not found"; a reviewer's own claim has no form;
  `npm run build` produces `out/`, and `npx serve out` works (upload, document viewer, sign-in)
  with no CSP errors in the console.

## Commit plan

- [x] 1. API side: `GET /claims/{id}/extraction` (`app/extraction/router.py`, `ExtractionRead`,
  `service.get_extraction`), `FRONTEND_ORIGINS` + `CORSMiddleware`, `python -m app.openapi`,
  committed `frontend/openapi.json`, `make openapi` (dump step), Terraform refresh token 8 hours —
  reviewer (extraction API rows), API shape (snapshot test) —
  `add extraction endpoint, cors for the frontend origins, openapi dump + snapshot test, 8 hour refresh token, tests`
- [x] 2. Frontend foundation: Next.js static export, Tailwind + shadcn/ui components, ESLint
  (`react/no-danger`), Vitest + RTL + MSW (`openapi-msw`), `gen:api` → `schema.d.ts`, `client.ts`
  (Bearer, 401 → signOut), `QueryState`, `StatusBadge`, CSP `<meta>`, env check at build,
  `make openapi` runs `gen:api`, CI `frontend` job — loading/error (`QueryState`), API shape (CI) —
  `add next.js frontend scaffold, generated api types and client, query state, csp, frontend ci job, tests`
- [x] 3. Auth: Amplify config, `AuthGate`, `useMe`, `pageAccess` + `PageGate`, `AppShell` nav by role,
  `/` redirect, admin notice, 404 page — login + roles —
  `add amplify authenticator gate, page access map and gate, app shell nav, role redirect, 404 page, tests`
- [x] 4. Employee pages: `ClaimList`, `NewClaimForm` + `uploadToS3`, `ClaimDetail` (polling, file
  link, reviewer comments), `AnswerForm`, routes `/claims`, `/claims/new`, `/claims/view` — employee,
  loading/error for these views —
  `add employee claim list, new claim form with s3 upload, claim detail with polling and needs_info answer, tests`
- [x] 5. Reviewer pages + demo: `ReviewQueue`, `ReviewClaim`, `DocumentViewer`, `ExtractionPanel`,
  `ProposalPanel`, `DecisionForm`, routes `/review`, `/review/claim`; README "Run the frontend" —
  reviewer, loading/error for these views —
  `add review queue, review claim page with document, extraction, proposal panels and decision form, comment required on reject, readme, tests`
