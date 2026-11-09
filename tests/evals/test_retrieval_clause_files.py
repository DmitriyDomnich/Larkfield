import json
from pathlib import Path

from evals.retrieval.clause_files import clause_file_text, clause_references, write_clause_files
from evals.retrieval.clauses import KB_DIR, clauses_in_chunk, load_clauses

CLAUSES = load_clauses()


def test_one_file_and_sidecar_per_clause(tmp_path: Path) -> None:
    written = write_clause_files(CLAUSES, KB_DIR, tmp_path)

    assert written == len(CLAUSES) == 184
    assert len(list(tmp_path.glob("*/*.md"))) == 184
    assert len(list(tmp_path.glob("*/*.md.metadata.json"))) == 184
    assert (tmp_path / "expense-policy" / "2.1.md").exists()
    assert (tmp_path / "employee-expenses-faq" / "FAQ-52.md").exists()


def test_file_starts_with_document_and_section_then_the_clause() -> None:
    text = clause_file_text(CLAUSES["3.5"])

    assert text.startswith("Expense Policy: 3. Travel\n\n**3.5 Hotels.** Hotel rooms")
    assert clauses_in_chunk(text, CLAUSES) == {"3.5"}


def test_sidecar_adds_the_clause_id_to_the_document_metadata(tmp_path: Path) -> None:
    write_clause_files(CLAUSES, KB_DIR, tmp_path)

    sidecar = tmp_path / "contractor-expense-policy" / "C3.3.md.metadata.json"

    assert json.loads(sidecar.read_text("utf-8")) == {
        "metadataAttributes": {
            "document": "contractor-expense-policy",
            "audience": "contractor",
            "binding": False,
            "clause_id": "C3.3",
        }
    }


def test_text_outside_clauses_is_left_out(tmp_path: Path) -> None:
    write_clause_files(CLAUSES, KB_DIR, tmp_path)
    everything = "\n".join(p.read_text("utf-8") for p in tmp_path.glob("*/*.md"))

    assert "## Appendix" not in everything
    assert "A dinner for EUR 52 during a trip to Hamburg" not in everything
    assert "**Engagement manager**" not in everything


def test_files_from_an_earlier_build_are_removed(tmp_path: Path) -> None:
    stale = tmp_path / "expense-policy" / "9.9.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", "utf-8")

    write_clause_files(CLAUSES, KB_DIR, tmp_path)

    assert not stale.exists()


def test_references_are_the_other_clauses_a_clause_mentions() -> None:
    ids = CLAUSES.keys()

    assert clause_references(CLAUSES["2.1"], ids) == ["2.2", "2.4"]
    assert clause_references(CLAUSES["7.4"], ids) == ["7.1"]
    assert clause_references(CLAUSES["IT2.4"], ids) == ["4.3", "7.1"]
    assert clause_references(CLAUSES["FAQ-14"], ids) == ["2.1", "2.2", "2.4"]


def test_contractor_ids_are_not_read_as_employee_ids() -> None:
    assert clause_references(CLAUSES["C2.3"], CLAUSES.keys()) == ["C8.4"]


def test_amounts_and_section_mentions_are_not_references() -> None:
    assert clause_references(CLAUSES["3.4"], CLAUSES.keys()) == []
    assert clause_references(CLAUSES["5.2"], CLAUSES.keys()) == []


def test_sidecar_lists_references_only_when_there_are_some(tmp_path: Path) -> None:
    write_clause_files(CLAUSES, KB_DIR, tmp_path)

    def attributes(path: str) -> dict[str, object]:
        sidecar = tmp_path / f"{path}.md.metadata.json"
        loaded: dict[str, object] = json.loads(sidecar.read_text("utf-8"))["metadataAttributes"]
        return loaded

    assert attributes("expense-policy/2.3")["references"] == ["2.2"]
    assert "references" not in attributes("expense-policy/3.4")
