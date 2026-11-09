import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"

Variant = Literal["unfiltered", "filtered"]
VARIANTS: tuple[Variant, ...] = ("unfiltered", "filtered")
QUESTION_GROUPS = {
    "single clause (1-25)": range(1, 26),
    "two clauses (26-35)": range(26, 36),
    "traps (36-40)": range(36, 41),
}


@dataclass(frozen=True)
class Question:
    number: int
    question: str
    required: frozenset[str]
    also_relevant: frozenset[str]
    traps: frozenset[str]


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    document: str


# strategy -> variant -> question number -> chunks in rank order
RawResults = dict[str, dict[Variant, dict[int, list[RetrievedChunk]]]]


def load_questions(path: Path = QUESTIONS_PATH) -> list[Question]:
    return [
        Question(
            number=row["number"],
            question=row["question"],
            required=frozenset(row["required"]),
            also_relevant=frozenset(row["also_relevant"]),
            traps=frozenset(row["traps"]),
        )
        for row in json.loads(path.read_text("utf-8"))
    ]
