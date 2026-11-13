import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agent_runtime import AgentsforBedrockRuntimeClient
    from mypy_boto3_bedrock_agent_runtime.type_defs import RetrievalFilterTypeDef

SEARCH_RESULTS_COUNT = 3

EMPLOYEE_AUDIENCE_FILTER: "RetrievalFilterTypeDef" = {
    "notEquals": {"key": "audience", "value": "contractor"}  # type: ignore[typeddict-item]
}


@dataclass(frozen=True)
class PolicyChunk:
    clause_id: str
    document: str
    text: str
    references: tuple[str, ...] = ()
    binding: bool = False

    @property
    def clause_text(self) -> str | None:
        """Clause text without the "<document>: <section>" line above it"""
        heading = self.text.find(f"**{self.clause_id} ")
        return self.text[heading:].strip() if heading >= 0 else None


class PolicyRetriever(Protocol):
    async def search(self, query: str) -> list[PolicyChunk]: ...

    async def clause(self, clause_id: str) -> PolicyChunk | None:
        """The binding clause with this id"""
        ...


class BedrockPolicyRetriever:
    def __init__(
        self,
        knowledge_base_id: str,
        region: str,
        client: "AgentsforBedrockRuntimeClient | None" = None,
    ) -> None:
        self._knowledge_base_id = knowledge_base_id
        self._client = client or boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
        )

    async def search(self, query: str) -> list[PolicyChunk]:
        return await self._retrieve(query, SEARCH_RESULTS_COUNT, EMPLOYEE_AUDIENCE_FILTER)

    async def clause(self, clause_id: str) -> PolicyChunk | None:
        by_id: RetrievalFilterTypeDef = {
            "andAll": [
                {"equals": {"key": "clause_id", "value": clause_id}},
                {"equals": {"key": "binding", "value": True}},
            ]
        }
        found = await self._retrieve(clause_id, 1, by_id)
        return found[0] if found and found[0].clause_id == clause_id else None

    async def _retrieve(
        self, query: str, results_count: int, retrieval_filter: "RetrievalFilterTypeDef"
    ) -> list[PolicyChunk]:
        response = await asyncio.to_thread(
            self._client.retrieve,
            knowledgeBaseId=self._knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": results_count,
                    "filter": retrieval_filter,
                }
            },
        )
        return [
            _chunk(result.get("metadata", {}), result["content"].get("text", ""))
            for result in response["retrievalResults"]
        ]


def _chunk(metadata: Mapping[str, Any], text: str) -> PolicyChunk:
    references = metadata.get("references") or []
    if isinstance(references, str):
        references = [references]
    return PolicyChunk(
        clause_id=str(metadata.get("clause_id", "")),
        document=str(metadata.get("document", "")),
        text=text,
        references=tuple(str(reference) for reference in references),
        binding=str(metadata.get("binding", "")).lower() == "true",
    )
