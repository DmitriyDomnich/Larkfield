import pytest

from evals.retrieval.clauses import load_clauses
from evals.retrieval.models import Question, RawResults, RetrievedChunk
from evals.retrieval.scoring import score_all, score_question, summarize_group

CLAUSES = load_clauses()


def chunk(*clause_ids: str, document: str = "expense-policy", score: float = 0.7) -> RetrievedChunk:
    return RetrievedChunk("\n".join(CLAUSES[i].text for i in clause_ids), score, document)


def question(
    number: int, required: set[str], also: set[str] | None = None, traps: set[str] | None = None
) -> Question:
    return Question(
        number,
        f"question {number}",
        frozenset(required),
        frozenset(also or ()),
        frozenset(traps or ()),
    )


def test_required_clause_in_the_top_k_is_full_recall() -> None:
    chunks = [chunk("1.5"), chunk("2.1"), chunk("3.1")]

    score = score_question(question(1, {"2.1"}), chunks, CLAUSES, 3)

    assert score.recall == 1
    assert score.missed == frozenset()
    assert score.precision == pytest.approx(1 / 3)


def test_two_clause_question_with_one_found_is_half_recall() -> None:
    score = score_question(question(26, {"2.2", "2.3"}), [chunk("2.2"), chunk("1.1")], CLAUSES, 3)

    assert score.recall == 0.5
    assert score.missed == {"2.3"}


def test_chunks_past_k_are_ignored() -> None:
    chunks = [chunk("1.1"), chunk("1.2"), chunk("1.3"), chunk("2.1")]

    assert score_question(question(1, {"2.1"}), chunks, CLAUSES, 3).recall == 0


def test_precision_counts_chunks_with_required_or_also_relevant_clauses() -> None:
    q = question(1, {"2.1"}, also={"FAQ-13"})
    chunks = [chunk("FAQ-13", document="employee-expenses-faq"), chunk("2.1", "2.2"), chunk("6.1")]

    assert score_question(q, chunks, CLAUSES, 3).precision == pytest.approx(2 / 3)


def test_precision_divides_by_k_when_fewer_chunks_come_back() -> None:
    assert score_question(question(22, {"FAQ-52"}), [chunk("FAQ-52")], CLAUSES, 3).precision == (
        pytest.approx(1 / 3)
    )


def test_a_cut_clause_does_not_count() -> None:
    words = CLAUSES["2.1"].text.split()
    cut = RetrievedChunk(" ".join(words[: len(words) // 2]), 0.7, "expense-policy")

    score = score_question(question(1, {"2.1"}), [cut], CLAUSES, 3)

    assert score.recall == 0
    assert score.chunk_clauses == (frozenset(),)


def test_trap_and_contractor_chunk_are_flagged() -> None:
    q = question(36, {"3.3", "0.4"}, traps={"C3.3"})
    chunks = [chunk("C3.3", document="contractor-expense-policy"), chunk("3.3"), chunk("0.4")]

    score = score_question(q, chunks, CLAUSES, 3)

    assert score.trap_hit
    assert score.contractor_chunk
    assert score.recall == 1


def test_contractor_chunk_without_the_trap_clause_is_not_a_trap_hit() -> None:
    q = question(40, {"1.2"}, traps={"C1.2"})

    score = score_question(q, [chunk("C2.1", document="contractor-expense-policy")], CLAUSES, 3)

    assert not score.trap_hit
    assert score.contractor_chunk


def test_group_summary_averages_and_rates_traps_over_trap_questions_only() -> None:
    plain = question(1, {"2.1"})
    trap = question(37, {"2.2"}, traps={"C2.2"})
    scores = [
        score_question(plain, [chunk("2.1")], CLAUSES, 3),
        score_question(trap, [chunk("C2.2", document="contractor-expense-policy")], CLAUSES, 3),
    ]

    group = summarize_group(scores, [plain, trap])

    assert group.questions == 2
    assert group.recall == 0.5
    assert group.precision == pytest.approx(1 / 6)
    assert group.trap_rate == 1
    assert group.contractor_rate == 0.5


def test_group_without_trap_questions_has_no_trap_rate() -> None:
    plain = question(1, {"2.1"})

    group = summarize_group([score_question(plain, [chunk("2.1")], CLAUSES, 3)], [plain])

    assert group.trap_rate is None


def test_score_all_scores_every_strategy_and_variant() -> None:
    q = question(1, {"2.1"})
    raw: RawResults = {
        "fixed": {"unfiltered": {1: [chunk("2.1")]}, "filtered": {1: []}},
        "semantic": {"filtered": {1: [chunk("1.1")]}},
    }

    scored = score_all(raw, [q], CLAUSES, 3)

    assert {run: [s.recall for s in s_list] for run, s_list in scored.items()} == {
        ("fixed", "unfiltered"): [1.0],
        ("fixed", "filtered"): [0.0],
        ("semantic", "filtered"): [0.0],
    }
