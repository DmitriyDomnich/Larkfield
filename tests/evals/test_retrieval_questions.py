from evals.retrieval.clauses import load_clauses
from evals.retrieval.models import QUESTION_GROUPS, load_questions

QUESTIONS = load_questions()


def test_there_are_forty_questions_numbered_in_order() -> None:
    assert [q.number for q in QUESTIONS] == list(range(1, 41))
    assert sorted(n for numbers in QUESTION_GROUPS.values() for n in numbers) == list(range(1, 41))


def test_every_referenced_clause_exists_in_the_knowledge_base() -> None:
    clause_ids = load_clauses().keys()

    for question in QUESTIONS:
        assert question.required, question.number
        assert question.required | question.also_relevant | question.traps <= clause_ids


def test_group_sizes_match_the_eval_cases() -> None:
    by_number = {q.number: q for q in QUESTIONS}

    assert all(len(by_number[n].required) == 1 for n in range(1, 26))
    assert all(len(by_number[n].required) == 2 for n in range(26, 36))


def test_only_questions_36_to_40_have_contractor_traps() -> None:
    with_traps = {q.number: q.traps for q in QUESTIONS if q.traps}

    assert with_traps == {
        36: {"C3.3"},
        37: {"C2.2"},
        38: {"C2.5"},
        39: {"C3.4"},
        40: {"C1.2"},
    }
