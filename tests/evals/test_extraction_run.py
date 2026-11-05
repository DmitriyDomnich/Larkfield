import asyncio
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from botocore.stub import Stubber

from app.extraction.extractor import (
    BedrockExtractor,
    ExtractionOutcome,
    InvalidExtraction,
    UnreadableDocument,
    ValidExtraction,
)
from app.extraction.pages import PageImage
from app.extraction.settings import WorkerSettings
from evals.extraction import __main__ as cli
from evals.extraction.documents import available_ids, load_document
from evals.extraction.estimate import estimate_usage, prompt_tokens
from evals.extraction.metering import DOCUMENT_USAGE, metered_client
from evals.extraction.models import EvalDocument, TokenUsage
from evals.extraction.pricing import MODEL_PRICES, ModelPrice, model_price
from evals.extraction.run import run_documents
from evals.extraction.scoring import SCORED_FIELDS
from tests.evals.docs import DOC_IDS
from tests.extraction.fakes import FakeExtractor, expense, label

PAGES = [PageImage(b"page", "png")]
D01 = EvalDocument("D01", expense("D01"), PAGES)
E10 = EvalDocument("E10", None, PAGES)


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")


@pytest.fixture
def worker_settings() -> WorkerSettings:
    return WorkerSettings()


def valid(doc_id: str, **changes: Any) -> ValidExtraction:
    return ValidExtraction(expense(doc_id, **changes), "model")


async def test_correct_extraction_passes_with_every_field() -> None:
    [result] = await run_documents([D01], FakeExtractor(valid("D01")), concurrency=1)

    assert result.outcome == "extracted"
    assert result.fields == dict.fromkeys(SCORED_FIELDS, True)
    assert result.passed
    assert result.latency_s is not None


async def test_one_wrong_field_fails_the_document() -> None:
    [result] = await run_documents([D01], FakeExtractor(valid("D01", total="18.40")), concurrency=1)

    assert result.fields is not None
    assert not result.fields["total"]
    assert not result.passed


@pytest.mark.parametrize(
    ("outcome", "name"),
    [(UnreadableDocument("Total cut off"), "unreadable"), (InvalidExtraction("bad"), "invalid")],
)
async def test_labelled_document_without_extraction_scores_every_field_wrong(
    outcome: ExtractionOutcome, name: str
) -> None:
    [result] = await run_documents([D01], FakeExtractor(outcome), concurrency=1)

    assert result.outcome == name
    assert result.fields == dict.fromkeys(SCORED_FIELDS, False)
    assert result.expense is None


async def test_unlabelled_document_passes_only_when_failed_with_a_reason() -> None:
    [unreadable] = await run_documents([E10], FakeExtractor(UnreadableDocument("cut")), 1)
    [extracted] = await run_documents([E10], FakeExtractor(valid("D01")), 1)

    assert unreadable.passed
    assert unreadable.detail == "cut"
    assert unreadable.fields is None
    assert not extracted.passed


async def test_unusable_file_is_not_sent_to_the_model() -> None:
    document = EvalDocument("E10", None, unusable_reason="The image could not be opened")
    extractor = FakeExtractor(valid("D01"))

    [result] = await run_documents([document], extractor, concurrency=1)

    assert extractor.calls == []
    assert result.outcome == "unusable_file"
    assert result.passed


async def test_an_error_is_recorded_and_the_other_documents_still_run() -> None:
    extractor = FakeExtractor(TimeoutError("read timed out"), valid("D01"))

    failed, extracted = await run_documents([D01, D01], extractor, concurrency=1)

    assert failed.outcome == "error"
    assert failed.detail == "TimeoutError"
    assert failed.fields == dict.fromkeys(SCORED_FIELDS, False)
    assert extracted.passed


class MeteredFake:
    """Records its tokens from a worker thread, as the botocore hook does"""

    def __init__(self, tokens: dict[bytes, int]) -> None:
        self.tokens = tokens
        self.in_flight = 0
        self.most_in_flight = 0

    async def extract_expense(self, pages: Sequence[PageImage]) -> ExtractionOutcome:
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        await asyncio.to_thread(self._record, self.tokens[pages[0].data])
        self.in_flight -= 1
        return valid("D01")

    @staticmethod
    def _record(tokens: int) -> None:
        DOCUMENT_USAGE.get().input_tokens += tokens


async def test_concurrent_documents_keep_their_own_token_usage_and_the_limit() -> None:
    documents = [EvalDocument(f"D{n}", None, [PageImage(bytes([n]), "png")]) for n in range(8)]
    extractor = MeteredFake({bytes([n]): 100 * n for n in range(8)})

    results = await run_documents(documents, extractor, concurrency=3)

    assert [r.usage.input_tokens for r in results] == [100 * n for n in range(8)]
    assert extractor.most_in_flight == 3


async def test_metered_client_records_bedrock_usage(worker_settings: WorkerSettings) -> None:
    client = metered_client(worker_settings)
    with Stubber(client) as stubber:
        for _ in range(2):  # an invalid answer, then a valid retry: both are paid for
            stubber.add_response(
                "converse",
                {
                    "output": {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "toolUse": {
                                        "toolUseId": "t1",
                                        "name": "record_expense",
                                        "input": label("D01") if _ else {"total": "x"},
                                    }
                                }
                            ],
                        }
                    },
                    "stopReason": "tool_use",
                    "usage": {"inputTokens": 4000, "outputTokens": 600, "totalTokens": 4600},
                    "metrics": {"latencyMs": 900},
                },
            )

        [result] = await run_documents([D01], BedrockExtractor(worker_settings, client), 1)

    assert result.passed
    assert result.usage == TokenUsage(input_tokens=8000, output_tokens=1200, attempts=2)


def test_usage_cost_uses_the_model_price() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=100_000)

    assert usage.cost(ModelPrice(Decimal(3), Decimal(15))) == Decimal("4.5")


def test_the_eval_model_has_a_price_and_an_unknown_one_fails() -> None:
    assert model_price("eu.anthropic.claude-sonnet-4-6") in MODEL_PRICES.values()
    with pytest.raises(KeyError, match="add it to MODEL_PRICES"):
        model_price("eu.anthropic.unknown-model")


def test_every_document_loads_with_its_label() -> None:
    assert available_ids() == DOC_IDS
    d01 = load_document("D01", max_pages=10)
    e10 = load_document("E10", max_pages=10)

    assert d01.label == expense("D01")
    assert len(d01.pages) == 1
    assert e10.label is None
    assert e10.pages[0].format == "jpeg"


def test_a_pdf_over_the_page_limit_is_unusable() -> None:
    document = load_document("E01", max_pages=1)

    assert document.pages == []
    assert document.unusable_reason is not None


def test_estimate_counts_the_prompt_and_the_pages() -> None:
    d01 = estimate_usage(load_document("D01", max_pages=10))
    e01 = estimate_usage(load_document("E01", max_pages=10))

    assert d01.input_tokens > prompt_tokens()
    assert e01.input_tokens > d01.input_tokens  # more pages
    assert e01.output_tokens > d01.output_tokens  # more items
    assert estimate_usage(EvalDocument("E10", None, unusable_reason="x")) == TokenUsage()


@pytest.fixture
def cli_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeExtractor:
    extractor = FakeExtractor(valid("D01"))
    monkeypatch.setenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr(cli, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(cli, "metered_client", lambda settings: None)
    monkeypatch.setattr(cli, "BedrockExtractor", lambda settings, client: extractor)
    return extractor


def test_cli_shows_the_estimate_and_runs_nothing_when_declined(
    cli_run: FakeExtractor,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["evals.extraction", "D01"])
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    cli.main()

    output = capsys.readouterr().out
    assert "Estimated cost: $" in output
    assert "Cancelled." in output
    assert cli_run.calls == []
    assert list(tmp_path.iterdir()) == []


def test_cli_with_yes_runs_without_asking_and_writes_the_report(
    cli_run: FakeExtractor, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def no_input(prompt: str) -> str:
        raise AssertionError("asked for confirmation despite --yes")

    monkeypatch.setattr("sys.argv", ["evals.extraction", "D01", "--yes"])
    monkeypatch.setattr("builtins.input", no_input)

    cli.main()

    [report] = tmp_path.iterdir()
    assert len(cli_run.calls) == 1
    assert report.name.startswith("extraction-")
    assert "| Documents with every field correct | 1/1 (100.0%) |" in report.read_text()
