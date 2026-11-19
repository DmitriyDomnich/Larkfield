# TNN — Title

**Goal:** <the ticket's goal, one sentence>. **Out of scope:** <the ticket's out of scope, plus anything
deferred while writing this spec, with the ticket it moves to>.

## Acceptance criteria

<!-- One row per acceptance criterion in the ticket, worded as in the ticket. "How" is the mechanism
(endpoint, component, rule), "Tested by" the test files that prove it. Every row needs a test. -->

| Criterion | How | Tested by |
|---|---|---|
| | | |

## Flow

<!-- Optional: the happy path and the main failures as a Mermaid diagram (GitHub renders it), about
15 lines: `sequenceDiagram` for requests between browser, API, AWS and workers; `flowchart` for
statuses and branches. Delete if the ticket has no flow worth drawing. -->

```mermaid
sequenceDiagram
```

## Design decisions

<!-- Every "Design decision" the ticket names, plus any other choice a reviewer would ask about.
Format: **Choice:** why. *Rejected:* the alternatives and why not. -->

- **<Choice>:** <why>. *Rejected:* <alternative> (<why not>).

## Questions

<!-- Every "Question for your spec" from the ticket, as a bold heading, answered with facts. Link the
docs that back an answer. No question may stay open. -->

- **<Question from the ticket>?** <answer>.

## Configuration

<!-- New settings (added to Settings and .env.example), env vars, Terraform modules/variables, IAM.
"None" if nothing changes. -->

## Known gaps

<!-- What this ticket knowingly leaves broken or risky, and how to recover or which ticket fixes it. -->

## Testing

- **Unit:** <what is covered without a DB or AWS>.
- **Integration:** <what needs PostgreSQL, marked `@pytest.mark.integration`>.
- **Manual:** <the end-to-end check run before the PR>.

## Results

<!-- Filled before the PR: how the manual run went (date, anything that failed) and the code
reviews, with what was fixed or left out. -->

## Commit plan

<!-- Filled by /implement for a ticket bigger than a couple of commits; delete otherwise.
One line per slice, ticked when its tests pass and it is committed. -->

- [ ] 1. <slice> — <acceptance criteria it covers> — `<commit message>`
