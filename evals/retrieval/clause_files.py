import json
import re
import shutil
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from evals.retrieval.clauses import KB_DIR, Clause, load_clauses

CLAUSE_FILES_DIR = Path(__file__).resolve().parents[2] / "build" / "kb-clauses"
# a policy id like 2.2, C8.4 or IT3.4; handing the case of C2.1-like not reading as 2.1
CLAUSE_REFERENCE = re.compile(r"(?<![\w.])(?:C|IT)?\d+\.\d+")
DOCUMENT_TITLES = {
    "expense-policy": "Expense Policy",
    "contractor-expense-policy": "Contractor Expense Policy",
    "it-equipment-procurement-policy": "IT Equipment and Procurement Policy",
    "employee-expenses-faq": "Employee Expenses FAQ",
}


def clause_file_text(clause: Clause) -> str:
    return f"{DOCUMENT_TITLES[clause.document]}: {clause.section}\n\n{clause.text}\n"


def clause_references(clause: Clause, known_ids: Collection[str]) -> list[str]:
    mentioned = CLAUSE_REFERENCE.findall(clause.text)
    return [
        clause_id
        for clause_id in dict.fromkeys(mentioned)
        if clause_id in known_ids and clause_id != clause.clause_id
    ]


def document_metadata(kb_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        path.name.removesuffix(".md.metadata.json"): json.loads(path.read_text("utf-8"))[
            "metadataAttributes"
        ]
        for path in kb_dir.glob("*.md.metadata.json")
    }


def write_clause_files(clauses: Mapping[str, Clause], kb_dir: Path, out_dir: Path) -> int:
    shutil.rmtree(out_dir, ignore_errors=True)
    metadata = document_metadata(kb_dir)
    for clause in clauses.values():
        folder = out_dir / clause.document
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{clause.clause_id}.md").write_text(clause_file_text(clause), "utf-8")
        attributes = {**metadata[clause.document], "clause_id": clause.clause_id}
        references = clause_references(clause, clauses.keys())
        if references:
            attributes["references"] = references
        sidecar = folder / f"{clause.clause_id}.md.metadata.json"
        sidecar.write_text(json.dumps({"metadataAttributes": attributes}, indent=2) + "\n", "utf-8")
    return len(clauses)


def main() -> None:
    written = write_clause_files(load_clauses(), KB_DIR, CLAUSE_FILES_DIR)
    print(f"Wrote {written} clause files to {CLAUSE_FILES_DIR}")


if __name__ == "__main__":
    main()
