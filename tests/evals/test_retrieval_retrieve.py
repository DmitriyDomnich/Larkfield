from pathlib import Path
from typing import Any

import pytest
from botocore.stub import Stubber

from evals.retrieval.models import Question, RawResults, RetrievedChunk
from evals.retrieval.retrieve import (
    load_raw,
    retrieval_client,
    retrieve_all,
    retrieve_chunks,
    save_raw,
)
from evals.retrieval.settings import RetrievalSettings

QUESTION = Question(1, "Dinner limit?", frozenset({"2.1"}), frozenset(), frozenset())
SCORES = (0.5, 0.25)


def response(*texts: str, document: str = "expense-policy") -> dict[str, Any]:
    return {
        "retrievalResults": [
            {"content": {"text": text}, "score": score, "metadata": {"document": document}}
            for text, score in zip(texts, SCORES, strict=False)
        ]
    }


def expected_request(kb_id: str, k: int, filtered: bool) -> dict[str, Any]:
    search: dict[str, Any] = {"numberOfResults": k}
    if filtered:
        search["filter"] = {"notEquals": {"key": "audience", "value": "contractor"}}
    return {
        "knowledgeBaseId": kb_id,
        "retrievalQuery": {"text": QUESTION.question},
        "retrievalConfiguration": {"vectorSearchConfiguration": search},
    }


def test_unfiltered_request_asks_for_k_chunks_and_parses_results() -> None:
    client = retrieval_client("eu-north-1")
    with Stubber(client) as stub:
        stub.add_response("retrieve", response("a", "b"), expected_request("KBFIXED001", 3, False))

        chunks = retrieve_chunks(client, "KBFIXED001", QUESTION.question, 3, "unfiltered")

    assert chunks == [
        RetrievedChunk("a", 0.5, "expense-policy"),
        RetrievedChunk("b", 0.25, "expense-policy"),
    ]


def test_filtered_request_excludes_the_contractor_audience() -> None:
    client = retrieval_client("eu-north-1")
    with Stubber(client) as stub:
        stub.add_response("retrieve", response(), expected_request("KBFIXED001", 5, True))

        assert retrieve_chunks(client, "KBFIXED001", QUESTION.question, 5, "filtered") == []


def test_missing_metadata_leaves_the_document_empty() -> None:
    client = retrieval_client("eu-north-1")
    with Stubber(client) as stub:
        stub.add_response(
            "retrieve",
            {"retrievalResults": [{"content": {"text": "x"}}]},
            expected_request("KBFIXED001", 3, False),
        )

        chunks = retrieve_chunks(client, "KBFIXED001", QUESTION.question, 3, "unfiltered")

    assert chunks == [RetrievedChunk("x", 0.0, "")]


def test_retrieve_all_runs_every_strategy_both_ways() -> None:
    client = retrieval_client("eu-north-1")
    with Stubber(client) as stub:
        for kb_id, name in (("KBFIXED001", "fixed"), ("KBSEMANT01", "semantic")):
            for filtered, label in ((False, "all"), (True, "emp")):
                request = expected_request(kb_id, 3, filtered)
                stub.add_response("retrieve", response(f"{name} {label}"), request)

        raw = retrieve_all(client, {"fixed": "KBFIXED001", "semantic": "KBSEMANT01"}, [QUESTION], 3)
        stub.assert_no_pending_responses()

    assert {s: {v: chunks[1][0].text for v, chunks in per.items()} for s, per in raw.items()} == {
        "fixed": {"unfiltered": "fixed all", "filtered": "fixed emp"},
        "semantic": {"unfiltered": "semantic all", "filtered": "semantic emp"},
    }


def test_raw_results_survive_a_save_and_load(tmp_path: Path) -> None:
    raw: RawResults = {
        "fixed": {"filtered": {1: [RetrievedChunk("**2.1 Meals.** text", 0.71, "expense-policy")]}}
    }
    path = tmp_path / "raw.json"

    save_raw(raw, path)

    assert load_raw(path) == raw


def test_settings_read_the_knowledge_base_ids_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-north-1")
    monkeypatch.setenv("POLICY_KB_IDS", '{"fixed": "KBFIXED001", "semantic": "KBSEMANT01"}')

    settings = RetrievalSettings(_env_file=None)

    assert settings.policy_kb_ids == {"fixed": "KBFIXED001", "semantic": "KBSEMANT01"}
    assert settings.aws_region == "eu-north-1"
