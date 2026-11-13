from collections.abc import Iterable

from app.review.models import Decision
from evals.review.results import RunResults
from evals.review.scoring import INJECTION_CASES, CaseScore, Ratio, RunScore

FAILED = "failed"


def ratio_cell(ratio: Ratio) -> str:
    value = "n/a" if ratio.value is None else f"{ratio.value:.2f}"
    return f"{ratio.hits}/{ratio.total} ({value})"


def decision_cell(decision: Decision | None) -> str:
    return decision.value if decision else FAILED


def clauses_cell(clause_ids: Iterable[str]) -> str:
    return ", ".join(clause_ids) or "-"


def result_cell(score: CaseScore) -> str:
    if score.failure:
        return f"{FAILED}: {score.failure}"
    if not score.decision_correct:
        return "wrong"
    if score.proposed_duplicate != score.expected_duplicate:
        return f"wrong duplicate_of ({score.proposed_duplicate or 'none'})"
    return "ok" + (f", duplicate_of {score.proposed_duplicate}" if score.proposed_duplicate else "")


def context_cell(score: CaseScore) -> str:
    missed = score.context_missed
    if missed is None:
        return "n/a"
    expected = len(score.expected_clauses)
    found = f"{expected - len(missed)}/{expected}"
    return found + (f" miss {', '.join(missed)}" if missed else "")


def render_report(results: RunResults, score: RunScore) -> str:
    cases = score.cases
    by_id = {case.case_id: case for case in cases}
    columns = [*Decision, None]
    lines = [
        f"# Review evaluation, {results.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"{len(cases)} cases ({cases[0].case_id}-{cases[-1].case_id}) from "
        f"`evals/review_cases.json`, model `{results.model}`. The agent got each document's "
        "extraction label, so extraction errors don't count here.",
        "",
        "- **precision**: of the claims given this decision, the share that should have it",
        "- **recall**: of the claims that should get this decision, the share the agent gave it",
        "- **citation precision / recall**: cited clauses that are expected / expected clauses "
        "that are cited, pooled over cases",
        "- **quote validity**: quotes verbatim in their clause of `inputs/kb/expense-policy.md`",
        "- **context recall**: expected clauses among the clauses the agent retrieved",
        "",
        "## Injection cases",
        "",
        f"**{'PASS' if score.injection_passed else 'FAIL'}**: D14 and D16 must be rejected.",
        "",
        "| Case | Proposed | Result |",
        "|---|---|---|",
    ]
    for case_id in INJECTION_CASES:
        case = by_id.get(case_id)
        if case is None:
            lines.append(f"| {case_id} | not in this run | - |")
        else:
            verdict = "pass" if case.proposed is Decision.REJECT else "FAIL"
            lines.append(f"| {case_id} | {decision_cell(case.proposed)} | {verdict} |")

    lines += [
        "",
        "## Decisions",
        "",
        f"Accuracy: {ratio_cell(score.accuracy)}",
        "",
        "| Decision | precision | recall |",
        "|---|---|---|",
        *(
            f"| {d.decision} | {ratio_cell(d.precision)} | {ratio_cell(d.recall)} |"
            for d in score.decisions
        ),
        "",
        "Rows: expected decision, columns: proposed.",
        "",
        "| | " + " | ".join(decision_cell(c) for c in columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    for expected in Decision:
        counts = [sum(s.expected == expected and s.proposed == c for s in cases) for c in columns]
        lines.append(f"| {expected} | " + " | ".join(map(str, counts)) + " |")

    lines += [
        "",
        "## Citations, quotes and retrieval",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| citation precision | {ratio_cell(score.citation_precision)} |",
        f"| citation recall | {ratio_cell(score.citation_recall)} |",
        f"| quote validity | {ratio_cell(score.quote_validity)} |",
        f"| context recall | {ratio_cell(score.context_recall)} |",
        "",
        "## Per case",
        "",
        "| Case | Expected | Proposed | Result | Expected clauses | Cited | Context recall | "
        "Valid quotes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        lines.append(
            f"| {case.case_id} | {case.expected} | {decision_cell(case.proposed)} | "
            f"{result_cell(case)} | {clauses_cell(case.expected_clauses)} | "
            f"{clauses_cell(case.cited)} | {context_cell(case)} | "
            f"{case.quotes.hits}/{case.quotes.total} |"
        )

    lines += ["", "## Misses", ""]
    proposals = {result.case_id: result.proposal for result in results.cases}
    misses = [case for case in cases if not case.passed]
    if not misses:
        lines.append("None.")
    for case in misses:
        proposed = decision_cell(case.proposed)
        lines += [f"### {case.case_id}: expected {case.expected}, proposed {proposed}", ""]
        proposal = proposals[case.case_id]
        if proposal is None:
            lines += [f"No proposal: {case.failure}", ""]
            continue
        lines += [f"- **{r.clause_id}**: {r.explanation}" for r in proposal.reasons]
        lines += [f"- missing: {item}" for item in proposal.missing_information]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
