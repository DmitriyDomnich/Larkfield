from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.review.proposal import ReviewProposal
from evals.review.cases import CaseSetName

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"

AgentPlacement = Literal["in-process", "agentcore"]


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    proposal: ReviewProposal | None
    retrieved_clauses: list[str] | None  # None when there is no proposal
    failure: str | None


class RunResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    model: str
    case_set: CaseSetName = "dev"
    agent_placement: AgentPlacement = "in-process"
    cases: list[CaseResult]


def save_results(results: RunResults, path: Path) -> None:
    path.write_text(results.model_dump_json(indent=2) + "\n", "utf-8")


def load_results(path: Path) -> RunResults:
    return RunResults.model_validate_json(path.read_text("utf-8"))


def latest_results(case_set: CaseSetName, reports_dir: Path = REPORTS_DIR) -> Path | None:
    """The set's in-process run that started last, whatever its file is called (e.g.
    review-baseline.json); AgentCore runs and their rechecks are compared against it, not with it"""
    started: dict[Path, datetime] = {}
    for path in reports_dir.glob("review-*.json"):
        run = load_results(path)
        if run.case_set == case_set and run.agent_placement == "in-process":
            started[path] = run.started_at
    return max(started, key=started.__getitem__, default=None)
