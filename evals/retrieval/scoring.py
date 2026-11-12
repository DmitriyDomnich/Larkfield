from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean

from evals.retrieval.clauses import Clause, clauses_in_chunk
from evals.retrieval.models import Question, RawResults, RetrievedChunk, Variant

CONTRACTOR_DOCUMENT = "contractor-expense-policy"


@dataclass(frozen=True)
class QuestionScore:
    number: int
    recall: float
    precision: float
    missed: frozenset[str]
    trap_hit: bool
    contractor_chunk: bool
    chunk_clauses: tuple[frozenset[str], ...]


@dataclass(frozen=True)
class GroupScore:
    questions: int
    recall: float
    precision: float
    trap_rate: float | None
    contractor_rate: float


def score_question(
    question: Question,
    chunks: Sequence[RetrievedChunk],
    clauses: Mapping[str, Clause],
    k: int,
) -> QuestionScore:
    top = chunks[:k]
    chunk_clauses = tuple(frozenset(clauses_in_chunk(c.text, clauses)) for c in top)
    found = frozenset().union(*chunk_clauses)
    relevant = question.required | question.also_relevant
    return QuestionScore(
        number=question.number,
        recall=len(question.required & found) / len(question.required),
        precision=sum(1 for ids in chunk_clauses if ids & relevant) / k,
        missed=question.required - found,
        trap_hit=bool(question.traps & found),
        contractor_chunk=any(c.document == CONTRACTOR_DOCUMENT for c in top),
        chunk_clauses=chunk_clauses,
    )


def summarize_group(scores: Sequence[QuestionScore], questions: Sequence[Question]) -> GroupScore:
    with_traps = {q.number for q in questions if q.traps}
    trap_scores = [s for s in scores if s.number in with_traps]
    return GroupScore(
        questions=len(scores),
        recall=fmean(s.recall for s in scores),
        precision=fmean(s.precision for s in scores),
        trap_rate=fmean(s.trap_hit for s in trap_scores) if trap_scores else None,
        contractor_rate=fmean(s.contractor_chunk for s in scores),
    )


def score_all(
    raw: RawResults,
    questions: Sequence[Question],
    clauses: Mapping[str, Clause],
    k: int,
) -> dict[tuple[str, Variant], list[QuestionScore]]:
    return {
        (strategy, variant): [
            score_question(q, per_question.get(q.number, []), clauses, k) for q in questions
        ]
        for strategy, per_variant in raw.items()
        for variant, per_question in per_variant.items()
    }
