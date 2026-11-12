from collections.abc import Mapping, Sequence
from datetime import datetime

from evals.retrieval.clauses import COVERAGE_THRESHOLD, Clause
from evals.retrieval.models import QUESTION_GROUPS, Question, RawResults, Variant
from evals.retrieval.scoring import GroupScore, QuestionScore, score_all, summarize_group

DOCUMENT_LABELS = {
    "expense-policy": "EP",
    "contractor-expense-policy": "CP",
    "it-equipment-procurement-policy": "IT",
    "employee-expenses-faq": "FAQ",
}

Run = tuple[str, Variant]


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def summary_rows(runs: Mapping[Run, GroupScore]) -> list[str]:
    return [
        f"| {strategy} | {variant} | {format_rate(group.recall)} | "
        f"{format_rate(group.precision)} | {format_rate(group.trap_rate)} | "
        f"{format_rate(group.contractor_rate)} |"
        for (strategy, variant), group in runs.items()
    ]


def score_cell(score: QuestionScore, k: int) -> str:
    relevant_chunks = round(score.precision * k)
    found = "ok" if not score.missed else "miss " + ", ".join(sorted(score.missed))
    trap = " +trap" if score.trap_hit else ""
    return f"{found} · {relevant_chunks}/{k}{trap}"


def chunk_cell(document: str, clause_ids: frozenset[str]) -> str:
    label = DOCUMENT_LABELS.get(document, document or "?")
    return f"{label} {', '.join(sorted(clause_ids)) or '-'}"


def render_report(
    raw: RawResults,
    questions: Sequence[Question],
    clauses: Mapping[str, Clause],
    k: int,
    started_at: datetime,
) -> str:
    scores = score_all(raw, questions, clauses, k)
    runs = list(scores)
    by_number = {q.number: q for q in questions}
    header = "| Strategy | Retrieval | recall | precision | trap rate | contractor chunk |"
    lines = [
        f"# Retrieval evaluation, {started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"{len(questions)} questions, top {k} chunks, a chunk contains a clause when it has the "
        f"clause heading and at least {COVERAGE_THRESHOLD:.0%} of its words. "
        "`filtered` excludes `audience = contractor`.",
        "",
        "- **recall**: share of required clauses in the top k, averaged over questions",
        "- **precision**: share of the top k chunks with a required or also-relevant clause",
        "- **trap rate**: share of questions 36-40 with their contractor look-alike in the top k",
        "- **contractor chunk**: share of questions with any contractor chunk in the top k",
        "",
        "## Summary",
        "",
        header,
        "|---|---|---|---|---|---|",
        *summary_rows({run: summarize_group(scores[run], questions) for run in runs}),
    ]

    for group_name, numbers in QUESTION_GROUPS.items():
        group_questions = [by_number[n] for n in numbers if n in by_number]
        if not group_questions:
            continue
        lines += ["", f"## {group_name}", "", header, "|---|---|---|---|---|---|"]
        lines += summary_rows(
            {
                run: summarize_group(
                    [s for s in scores[run] if s.number in numbers], group_questions
                )
                for run in runs
            }
        )

    run_names = [f"{strategy} {variant}" for strategy, variant in runs]
    lines += [
        "",
        "## Per question",
        "",
        "`ok` / `miss <ids>`, then chunks with a relevant clause out of k; "
        "`+trap` when the contractor look-alike was retrieved.",
        "",
        "| # | Required | " + " | ".join(run_names) + " |",
        "|---|---|" + "---|" * len(runs),
    ]
    for index, question in enumerate(questions):
        cells = [score_cell(scores[run][index], k) for run in runs]
        required = ", ".join(sorted(question.required))
        lines.append(f"| {question.number} | {required} | " + " | ".join(cells) + " |")

    for run in runs:
        strategy, variant = run
        lines += [
            "",
            f"## Retrieved: {strategy} {variant}",
            "",
            "Document and the whole clauses each chunk contains, in rank order.",
            "",
            "| # | Question | " + " | ".join(f"rank {r}" for r in range(1, k + 1)) + " |",
            "|---|---|" + "---|" * k,
        ]
        for index, question in enumerate(questions):
            chunks = raw[strategy][variant].get(question.number, [])[:k]
            clause_sets = scores[run][index].chunk_clauses
            cells = [
                chunk_cell(chunk.document, ids)
                for chunk, ids in zip(chunks, clause_sets, strict=True)
            ]
            cells += [""] * (k - len(cells))
            lines.append(f"| {question.number} | {question.question} | " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"
