from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.extraction.schemas import ExtractedExpense, LineItem
from evals.extraction.models import DocumentResult
from evals.extraction.pricing import ModelPrice
from evals.extraction.scoring import (
    SCORED_FIELDS,
    ItemKey,
    item_key,
    nearest_rank_percentile,
    normalize_text,
)

COST_PLACES = Decimal("0.000001")
ITEM_ATTRIBUTES = ("quantity", "unit_price", "amount")
MAX_EXAMPLES = 3


@dataclass(frozen=True)
class RunInfo:
    started_at: datetime
    model: str
    concurrency: int
    estimated_cost: Decimal


@dataclass(frozen=True)
class Summary:
    labelled: int
    fully_correct: int
    field_correct: dict[str, int]
    unlabelled_passed: dict[str, bool]
    total_cost: Decimal
    cost_per_document: Decimal
    latency_p50_s: float | None
    latency_p95_s: float | None
    retried: int
    input_tokens: int
    output_tokens: int


def summarize(results: Sequence[DocumentResult], price: ModelPrice) -> Summary:
    labelled = [r for r in results if r.fields is not None]
    field_correct = Counter(field for r in labelled for field, ok in (r.fields or {}).items() if ok)
    latencies = [r.latency_s for r in results if r.latency_s is not None]
    total_cost = sum((r.usage.cost(price) for r in results), Decimal(0))
    return Summary(
        labelled=len(labelled),
        fully_correct=sum(r.passed for r in labelled),
        field_correct={field: field_correct[field] for field in SCORED_FIELDS},
        unlabelled_passed={r.doc_id: r.passed for r in results if r.fields is None},
        total_cost=total_cost,
        cost_per_document=total_cost / len(results) if results else Decimal(0),
        latency_p50_s=nearest_rank_percentile(latencies, 0.5) if latencies else None,
        latency_p95_s=nearest_rank_percentile(latencies, 0.95) if latencies else None,
        retried=sum(r.usage.attempts > 1 for r in results),
        input_tokens=sum(r.usage.input_tokens for r in results),
        output_tokens=sum(r.usage.output_tokens for r in results),
    )


def _share(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.1%})" if whole else "n/a"


def _seconds(value: float | None) -> str:
    return f"{value:.1f} s" if value is not None else "n/a"


def format_usd(value: Decimal) -> str:
    return f"${value.quantize(COST_PLACES)}"


def _cell(value: object) -> str:
    text = "null" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _item_count(items: Sequence[LineItem]) -> str:
    return f"{len(items)} item" if len(items) == 1 else f"{len(items)} items"


def _examples(texts: Sequence[str]) -> str:
    shown = "; ".join(texts[:MAX_EXAMPLES])
    hidden = len(texts) - MAX_EXAMPLES
    return f"{shown}; and {hidden} more" if hidden > 0 else shown


def _unmatched(items: Sequence[LineItem], matched: Counter[ItemKey]) -> list[LineItem]:
    remaining = matched.copy()
    unmatched = []
    for item in items:
        key = item_key(item)
        if remaining[key]:
            remaining[key] -= 1
        else:
            unmatched.append(item)
    return unmatched


def _items_difference(expected: ExtractedExpense, actual: ExtractedExpense) -> tuple[str, str]:
    matched = Counter(map(item_key, expected.line_items)) & Counter(
        map(item_key, actual.line_items)
    )
    missing = _unmatched(expected.line_items, matched)
    unexpected = _unmatched(actual.line_items, matched)

    differing: dict[str, list[str]] = {}
    for want in list(missing):
        description = normalize_text(want.description)
        got = next((i for i in unexpected if normalize_text(i.description) == description), None)
        if got is None:
            continue
        missing.remove(want)
        unexpected.remove(got)
        for attribute in ITEM_ATTRIBUTES:
            want_value, got_value = getattr(want, attribute), getattr(got, attribute)
            if want_value != got_value:
                differing.setdefault(attribute, []).append(
                    f"{want.description}: {_cell(want_value)} vs {_cell(got_value)}"
                )

    problems = [
        f"{attribute} differs on {len(examples)}: {_examples(examples)}"
        for attribute, examples in differing.items()
    ]
    for name, items in (("missing", missing), ("unexpected", unexpected)):
        if items:
            problems.append(f"{name} {len(items)}: {_examples([i.description for i in items])}")
    return _item_count(expected.line_items), "<br>".join(
        [_item_count(actual.line_items), *problems]
    )


def mismatches(
    results: Sequence[DocumentResult], labels: dict[str, ExtractedExpense]
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for result in results:
        if result.fields is None or result.expense is None:
            continue
        label = labels[result.doc_id]
        for field, ok in result.fields.items():
            if ok:
                continue
            expected: object
            got: object
            if field == "line_items":
                expected, got = _items_difference(label, result.expense)
            else:
                expected, got = getattr(label, field), getattr(result.expense, field)
            rows.append((result.doc_id, field, _cell(expected), _cell(got)))
    return rows


def render_markdown(
    results: Sequence[DocumentResult],
    labels: dict[str, ExtractedExpense],
    summary: Summary,
    info: RunInfo,
    price: ModelPrice,
) -> str:
    lines = [
        f"# Extraction eval — {info.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"- Model: `{info.model}`",
        f"- Documents: {len(results)} ({summary.labelled} labelled)",
        f"- Concurrency: {info.concurrency}",
        f"- Prices (USD per million tokens): input {price.input_per_mtok}, "
        f"output {price.output_per_mtok}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Documents with every field correct | "
        f"{_share(summary.fully_correct, summary.labelled)} |",
    ]
    lines += [
        f"| {doc_id} failed with a reason | {'yes' if passed else 'no'} |"
        for doc_id, passed in summary.unlabelled_passed.items()
    ]
    lines += [
        f"| Cost per document | {format_usd(summary.cost_per_document)} |",
        f"| Total cost (estimated before run) | {format_usd(summary.total_cost)} "
        f"({format_usd(info.estimated_cost)}) |",
        f"| Documents needing more than one attempt | {summary.retried} |",
        f"| Tokens in / out | {summary.input_tokens} / {summary.output_tokens} |",
        f"| Latency p50 / p95 | {_seconds(summary.latency_p50_s)} / "
        f"{_seconds(summary.latency_p95_s)} |",
        "",
        "## Per-field accuracy",
        "",
        "| Field | Correct |",
        "| --- | --- |",
    ]
    lines += [
        f"| {field} | {_share(correct, summary.labelled)} |"
        for field, correct in summary.field_correct.items()
    ]

    rows = mismatches(results, labels)
    lines += ["", "## Mismatches", ""]
    if rows:
        lines += ["| Doc | Field | Expected | Got |", "| --- | --- | --- | --- |"]
        lines += [f"| {doc} | {field} | {expected} | {got} |" for doc, field, expected, got in rows]
    else:
        lines.append("None.")

    lines += [
        "",
        "## Per document",
        "",
        "| Doc | Outcome | Fields correct | Attempts | Latency | Tokens in / out | Cost | Detail |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        correct = _share(sum(r.fields.values()), len(r.fields)) if r.fields else "-"
        lines.append(
            f"| {r.doc_id} | {r.outcome} | {correct} | {r.usage.attempts} | "
            f"{_seconds(r.latency_s)} | "
            f"{r.usage.input_tokens} / {r.usage.output_tokens} | "
            f"{format_usd(r.usage.cost(price))} | {_cell(r.detail or '')} |"
        )
    return "\n".join(lines) + "\n"
