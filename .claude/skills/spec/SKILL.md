---
name: spec
description: Write specs/TNN-*.md for a ticket from specs/_template.md, interviewing the developer until every question and design decision in the ticket is answered
argument-hint: TNN [pasted ticket text]
disable-model-invocation: true
---

Write the spec for: $ARGUMENTS

The spec is written before any code and is what `/implement` builds from, so it must leave nothing
to guess. You draft; the developer decides. Don't write code or touch files other than the spec.

## 1. Get the ticket
- The ticket number is the first word (`T13`). The ticket text follows it. If there is no text, ask
  the developer to paste the ticket (goal, acceptance criteria, design decisions, questions for the
  spec, out of scope) and stop until they do.
- If `specs/TNN-*.md` already exists, read it and continue from it instead of starting over.
- Slug: 2-4 words from the ticket title, kebab-case (`T12-reviewer-decisions-notifications.md`).

## 2. Learn what exists
Before asking anything, find out what you can answer yourself:
- `CLAUDE.md`, the specs this ticket builds on (read the 2-3 most related ones in `specs/`, and the
  latest one for tone and length), and the code they describe: routers, schemas, models, settings,
  `infra/`, `.github/workflows/ci.yml`.
- For AWS behaviour use the `aws-docs` MCP tools; for libraries, the official docs. Note the URLs:
  answers in the spec cite them.
- List the open points: every "Question for your spec", every named "Design decision", and anything
  the acceptance criteria leave ambiguous (roles, error cases, limits, what the UI shows when).

## 3. Write the skeleton
Copy `specs/_template.md` to `specs/TNN-<slug>.md` and fill what the ticket fixes: title, goal, out
of scope, and one acceptance-criteria row per criterion with "How" and "Tested by" left empty.

## 4. Interview
Grill the developer until every open point is decided. Rules:
- **One question at a time**, with `AskUserQuestion`. Order: the decisions others depend on first
  (architecture, where things run, data shapes), details last.
- **Bring a recommendation.** 2-4 concrete options from what you learned in step 2, the recommended
  one first, each with its trade-off in one line. Use `preview` for code or layout comparisons.
- **Don't ask what the code, the docs or a convention already answer.** State the answer instead
  and let the developer object.
- **Push back** on an answer that is vague ("secure enough", "handle errors"), contradicts an
  earlier answer, `CLAUDE.md` or an existing spec, or leaves an acceptance criterion untestable. Ask
  the follow-up: what exactly happens, who can do it, what the test checks.
- For each "Question for your spec", make the developer commit to a factual answer, including the
  uncomfortable part (what an attacker gets, what breaks, what it costs). If it needs a fact you
  can look up, look it up and propose the answer.
- After each answer, write it into the spec right away (design decision with *Rejected*
  alternatives, question answer, acceptance-criteria "How"), so the file is never behind the talk.
- Stop asking when every open point is answered and every acceptance criterion has a "How" and a
  "Tested by". Don't pad the interview with questions that change nothing.

## 5. Finish the spec
- Fill Flow (or delete it), Configuration, Known gaps and Testing. Delete the template's HTML
  comments and the Commit plan section (`/implement` adds it).
- Match the existing specs: terse, facts over prose, about one screen per section, no filler.
- Re-read the ticket line by line and check each criterion, decision and question is covered.

## 6. Report
- The spec's path.
- The decisions made, one line each.
- Anything deferred to Known gaps or another ticket.
- Next step: `/implement TNN` in a fresh session.

Never stage, commit or push.
