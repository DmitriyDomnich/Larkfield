import re
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

KB_DIR = Path(__file__).resolve().parents[2] / "inputs" / "kb"
COVERAGE_THRESHOLD = 0.8

CLAUSE_HEADING = re.compile(r"^\*\*(?P<id>(?:C|IT)?\d+\.\d+|FAQ-\d+)\.?\s.*?\*\*", re.MULTILINE)
SECTION_HEADING = re.compile(r"^#+\s*(?P<title>.*)$", re.MULTILINE)
MARKDOWN_MARKS = re.compile(r"[*`#]")


@dataclass(frozen=True)
class Clause:
    clause_id: str
    document: str
    heading: str
    text: str
    section: str = ""


def normalize(text: str) -> str:
    return " ".join(MARKDOWN_MARKS.sub("", text).lower().split())


def parse_clauses(markdown: str, document: str) -> list[Clause]:
    headings = list(CLAUSE_HEADING.finditer(markdown))
    sections = list(SECTION_HEADING.finditer(markdown))
    clauses = []
    for index, match in enumerate(headings):
        next_heading = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        next_section = next((s for s in sections if match.end() <= s.start() < next_heading), None)
        own_section = next((s for s in reversed(sections) if s.start() < match.start()), None)
        clauses.append(
            Clause(
                clause_id=match["id"],
                document=document,
                heading=normalize(match[0]),
                text=markdown[
                    match.start() : next_section.start() if next_section else next_heading
                ].strip(),
                section=own_section["title"].strip() if own_section else "",
            )
        )
    return clauses


def load_clauses(kb_dir: Path = KB_DIR) -> dict[str, Clause]:
    clauses: dict[str, Clause] = {}
    for path in sorted(kb_dir.glob("*.md")):
        for clause in parse_clauses(path.read_text("utf-8"), path.stem):
            if clause.clause_id in clauses:
                raise ValueError(f"clause {clause.clause_id} appears twice ({path.name})")
            clauses[clause.clause_id] = clause
    return clauses


def has_heading(normalized_chunk: str, clause: Clause) -> bool:
    return re.search(rf"(?<![\w.-]){re.escape(clause.heading)}", normalized_chunk) is not None


def text_coverage(normalized_chunk: str, clause: Clause) -> float:
    clause_words = normalize(clause.text).split()
    matcher = SequenceMatcher(None, clause_words, normalized_chunk.split(), autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(clause_words)


def clauses_in_chunk(chunk_text: str, clauses: Mapping[str, Clause]) -> set[str]:
    normalized_chunk = normalize(chunk_text)
    return {
        clause_id
        for clause_id, clause in clauses.items()
        if has_heading(normalized_chunk, clause)
        and text_coverage(normalized_chunk, clause) >= COVERAGE_THRESHOLD
    }
