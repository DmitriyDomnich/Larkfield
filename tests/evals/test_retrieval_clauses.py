import json
from collections import Counter
from pathlib import Path

import pytest

from evals.retrieval.clauses import (
    KB_DIR,
    Clause,
    clauses_in_chunk,
    load_clauses,
    normalize,
    parse_clauses,
)

CLAUSES = load_clauses()
EXPENSE_POLICY_IDS = {
    "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7",
    "1.1", "1.2", "1.3", "1.4", "1.5",
    "2.1", "2.2", "2.3", "2.4", "2.5",
    "3.1", "3.2", "3.3", "3.4", "3.5", "3.6",
    "4.1", "4.2", "4.3",
    "5.1", "5.2",
    "6.1", "6.2", "6.3", "6.4",
    "7.1", "7.2", "7.3", "7.4",
}  # fmt: skip


def test_every_document_is_parsed_into_its_clauses() -> None:
    per_document = Counter(clause.document for clause in CLAUSES.values())

    assert per_document == {
        "expense-policy": 36,
        "contractor-expense-policy": 46,
        "it-equipment-procurement-policy": 47,
        "employee-expenses-faq": 55,
    }
    expense_ids = {c.clause_id for c in CLAUSES.values() if c.document == "expense-policy"}
    assert expense_ids == EXPENSE_POLICY_IDS
    assert {f"FAQ-{n}" for n in range(1, 56)} <= CLAUSES.keys()
    assert {"C1.1", "C8.5", "IT1.1", "IT9.7"} <= CLAUSES.keys()


def test_clause_text_stops_at_the_next_clause_or_section() -> None:
    assert CLAUSES["0.7"].text.endswith("limits apply to the converted amount.")
    assert "Appendix" not in CLAUSES["7.4"].text
    assert "Hamburg" not in CLAUSES["7.4"].text
    assert CLAUSES["C8.5"].text.endswith("a statement of work that names the exception can do so.")


def test_clause_knows_its_section_heading() -> None:
    assert CLAUSES["3.5"].section == "3. Travel"
    assert CLAUSES["FAQ-13"].section == "Meals and entertainment"
    assert CLAUSES["IT9.7"].section == "9. Purchasing from suppliers above EUR 5,000"


def test_faq_clause_holds_question_and_answer() -> None:
    faq = CLAUSES["FAQ-52"]

    assert faq.heading == "faq-52. how long does finance take to review a claim?"
    assert "Finance aims for 5 working days." in faq.text
    assert "FAQ-53" not in faq.text


def test_duplicate_clause_id_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("**2.1 Meals.** One.\n", "utf-8")
    (tmp_path / "b.md").write_text("**2.1 Meals.** Two.\n", "utf-8")

    with pytest.raises(ValueError, match=r"2\.1"):
        load_clauses(tmp_path)


def test_whole_clause_in_a_chunk_is_found() -> None:
    chunk = f"{CLAUSES['2.5'].text}\n\n## 3. Travel\n\n{CLAUSES['3.1'].text[:60]}"

    assert clauses_in_chunk(chunk, CLAUSES) == {"2.5"}


def test_two_whole_clauses_are_both_found() -> None:
    chunk = f"{CLAUSES['2.1'].text}\n\n{CLAUSES['2.2'].text}"

    assert clauses_in_chunk(chunk, CLAUSES) == {"2.1", "2.2"}


def test_clause_is_found_without_markdown_and_with_other_line_breaks() -> None:
    plain = normalize(CLAUSES["3.3"].text).upper().replace(" ", "\n", 10)

    assert clauses_in_chunk(plain, CLAUSES) == {"3.3"}


def test_clause_split_across_chunks_is_found_in_neither_half() -> None:
    words = CLAUSES["1.3"].text.split()
    first_half = " ".join(words[: len(words) // 2])
    second_half = " ".join(words[len(words) // 2 :])

    assert clauses_in_chunk(first_half, CLAUSES) == set()
    assert clauses_in_chunk(second_half, CLAUSES) == set()


def test_heading_without_most_of_the_text_is_not_found() -> None:
    chunk = "**2.1 Meals during business trips.** During a business trip, Larkfield reimburses"

    assert clauses_in_chunk(chunk, CLAUSES) == set()


def test_mention_of_a_clause_id_is_not_the_clause() -> None:
    chunk = CLAUSES["IT2.4"].text

    assert "clause 4.3" in chunk
    assert clauses_in_chunk(chunk, CLAUSES) == {"IT2.4"}


def test_contractor_clause_is_not_the_employee_clause_with_the_same_number() -> None:
    assert CLAUSES["C3.6"].heading.endswith("3.6 hotel extras.")

    assert clauses_in_chunk(CLAUSES["C3.6"].text, CLAUSES) == {"C3.6"}
    assert clauses_in_chunk(CLAUSES["3.6"].text, CLAUSES) == {"3.6"}


def test_parse_ignores_bullets_and_plain_paragraphs() -> None:
    markdown = "## Definitions\n\n- **Contractor**: someone.\n\nAll amounts are in euros.\n"

    assert parse_clauses(markdown, "doc") == []


def test_parsed_clause_keeps_its_document_and_raw_text() -> None:
    markdown = "## 2. Meals\n\n**2.5 Tips.** Up to 10%.\n\n## Appendix A. Examples\n\n- Example.\n"

    assert parse_clauses(markdown, "doc") == [
        Clause(
            "2.5",
            document="doc",
            heading="2.5 tips.",
            text="**2.5 Tips.** Up to 10%.",
            section="2. Meals",
        )
    ]


@pytest.mark.parametrize("path", sorted(KB_DIR.glob("*.md")), ids=lambda path: path.stem)
def test_every_document_has_metadata_matching_its_file(path: Path) -> None:
    sidecar = path.with_name(f"{path.name}.metadata.json")
    attributes = json.loads(sidecar.read_text("utf-8"))["metadataAttributes"]

    assert attributes["document"] == path.stem
    assert attributes["audience"] in {"employee", "contractor"}
    assert attributes["binding"] is (path.stem == "expense-policy")
