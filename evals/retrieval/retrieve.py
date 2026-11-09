import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from evals.retrieval.models import VARIANTS, Question, RawResults, RetrievedChunk, Variant

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agent_runtime import AgentsforBedrockRuntimeClient
    from mypy_boto3_bedrock_agent_runtime.type_defs import (
        KnowledgeBaseVectorSearchConfigurationTypeDef,
        RetrievalFilterTypeDef,
    )

EMPLOYEE_AUDIENCE_FILTER: "RetrievalFilterTypeDef" = {
    "notEquals": {"key": "audience", "value": "contractor"}  # type: ignore[typeddict-item]
}


def retrieval_client(region: str) -> "AgentsforBedrockRuntimeClient":
    return boto3.client(
        "bedrock-agent-runtime",
        region_name=region,
        config=Config(retries={"max_attempts": 10, "mode": "adaptive"}),
    )


def retrieve_chunks(
    client: "AgentsforBedrockRuntimeClient",
    knowledge_base_id: str,
    question: str,
    k: int,
    variant: Variant,
) -> list[RetrievedChunk]:
    search: KnowledgeBaseVectorSearchConfigurationTypeDef = {"numberOfResults": k}
    if variant == "filtered":
        search["filter"] = EMPLOYEE_AUDIENCE_FILTER
    response = client.retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": question},
        retrievalConfiguration={"vectorSearchConfiguration": search},
    )
    return [
        RetrievedChunk(
            text=result["content"].get("text", ""),
            score=result.get("score", 0.0),
            document=str(result.get("metadata", {}).get("document", "")),
        )
        for result in response["retrievalResults"]
    ]


def retrieve_all(
    client: "AgentsforBedrockRuntimeClient",
    knowledge_base_ids: Mapping[str, str],
    questions: Sequence[Question],
    k: int,
) -> RawResults:
    return {
        strategy: {
            variant: {
                question.number: retrieve_chunks(client, kb_id, question.question, k, variant)
                for question in questions
            }
            for variant in VARIANTS
        }
        for strategy, kb_id in knowledge_base_ids.items()
    }


def save_raw(raw: RawResults, path: Path) -> None:
    serializable = {
        strategy: {
            variant: {
                str(number): [asdict(chunk) for chunk in chunks]
                for number, chunks in per_question.items()
            }
            for variant, per_question in per_variant.items()
        }
        for strategy, per_variant in raw.items()
    }
    path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False) + "\n", "utf-8")


def load_raw(path: Path) -> RawResults:
    data = json.loads(path.read_text("utf-8"))
    return {
        strategy: {
            variant: {
                int(number): [RetrievedChunk(**chunk) for chunk in chunks]
                for number, chunks in per_question.items()
            }
            for variant, per_question in per_variant.items()
        }
        for strategy, per_variant in data.items()
    }
