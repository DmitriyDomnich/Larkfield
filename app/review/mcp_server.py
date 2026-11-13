import asyncio
import copy
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from strands.middleware import ToolResultEvent
from strands.types.tools import ToolUse

from app.core.db import build_engine, build_session_factory
from app.review.agent import CLAIM_TOOLS, ReviewRun
from app.review.claim_data import ClaimUnderReview, load_claim_of_any_status
from app.review.claims_history import ClaimsHistory, DatabaseClaimsHistory
from app.review.policy import BedrockPolicyRetriever, PolicyRetriever
from app.review.settings import ReviewToolsSettings

logger = logging.getLogger(__name__)

SERVER_NAME = "larkfield-review"
SERVER_INSTRUCTIONS = (
    "The review agent's tools, run as the agent would run them. The claim tools take a claim_id "
    "(any status): use them to see what the agent saw when it made a proposal."
)
CLAIM_ID_PARAM = "claim_id"
CLAIM_ID_SCHEMA = {
    "type": "string",
    "format": "uuid",
    "description": "The claim the tool runs for, as in a review of that claim.",
}

ClaimLoader = Callable[[uuid.UUID], Awaitable[ClaimUnderReview | None]]


class NoAgent:
    """Stands in for the agent a tool cancels when its lookup fails; the failure is read from
    `ReviewRun.failure` instead"""

    def cancel(self) -> None:
        pass


class ReviewTools:
    def __init__(
        self, retriever: PolicyRetriever, history: ClaimsHistory, load_claim: ClaimLoader
    ) -> None:
        self._retriever = retriever
        self._history = history
        self._load_claim = load_claim

    def get_mcp_tool_specs(self) -> list[Tool]:
        run = ReviewRun(None, self._retriever, self._history)
        return [_get_mcp_tool_spec(agent_tool.tool_spec) for agent_tool in run.tools()]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        tool_input = dict(arguments)
        claim = None
        if name in CLAIM_TOOLS:
            try:
                claim_id = uuid.UUID(str(tool_input.pop(CLAIM_ID_PARAM)))
            except (KeyError, ValueError):
                return _build_error_result(f"{CLAIM_ID_PARAM} must be a claim id (UUID)")
            claim = await self._load_claim(claim_id)
            if claim is None:
                return _build_error_result(f"There is no claim {claim_id} with an extraction.")

        run = ReviewRun(claim, self._retriever, self._history)
        agent_tool = next((t for t in run.tools() if t.tool_name == name), None)
        if agent_tool is None:
            return _build_error_result(f"There is no tool {name!r}.")
        result = await _run_agent_tool(agent_tool, tool_input)

        if run.failure is not None:
            return _build_error_result(
                f"The tool failed ({type(run.failure).__name__}); the server log has the details."
            )
        if result.exception is None:
            return CallToolResult(content=[TextContent(type="text", text=_get_text(result))])
        if isinstance(result.exception, ValueError):
            # invalid arguments: the message the agent would get
            return _build_error_result(_get_text(result))
        logger.error("tool %s failed", name, exc_info=result.exception)
        return _build_error_result(
            f"The tool failed ({type(result.exception).__name__}); the server log has the details."
        )


async def _run_agent_tool(agent_tool: Any, tool_input: dict[str, Any]) -> ToolResultEvent:
    """Runs the tool as the agent loop does: Strands validates the input and catches errors"""
    tool_use: ToolUse = {
        "toolUseId": str(uuid.uuid4()),
        "name": agent_tool.tool_name,
        "input": tool_input,
    }
    results = [
        event
        async for event in agent_tool.stream(tool_use, {"agent": NoAgent()})
        if isinstance(event, ToolResultEvent)
    ]
    return results[-1]


def build_server(tools: ReviewTools) -> Server[Any]:
    mcp_tool_specs = tools.get_mcp_tool_specs()

    async def list_tools(
        _ctx: ServerRequestContext[Any], _params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=mcp_tool_specs)

    async def call_tool(
        _ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult:
        return await tools.call_tool(params.name, params.arguments or {})

    return Server(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def _get_mcp_tool_spec(agent_tool_spec: Any) -> Tool:
    schema: dict[str, Any] = copy.deepcopy(agent_tool_spec["inputSchema"]["json"])
    if agent_tool_spec["name"] in CLAIM_TOOLS:
        schema.setdefault("type", "object")
        schema["properties"] = {CLAIM_ID_PARAM: CLAIM_ID_SCHEMA, **schema.get("properties", {})}
        schema["required"] = [CLAIM_ID_PARAM, *schema.get("required", [])]
    return Tool(
        name=agent_tool_spec["name"],
        description=agent_tool_spec["description"],
        input_schema=schema,
    )


def _get_text(result: ToolResultEvent) -> str:
    return "\n".join(block.get("text", "") for block in result.tool_result["content"])


def _build_error_result(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


async def serve() -> None:
    settings = ReviewToolsSettings()
    logging.basicConfig(level=settings.log_level)
    engine = build_engine(settings)
    sessions = build_session_factory(engine.execution_options(postgresql_readonly=True))

    async def load_claim(claim_id: uuid.UUID) -> ClaimUnderReview | None:
        async with sessions() as session:
            return await load_claim_of_any_status(session, claim_id)

    try:
        retriever = await asyncio.to_thread(
            BedrockPolicyRetriever, settings.policy_kb_id, settings.aws_region
        )
        server = build_server(ReviewTools(retriever, DatabaseClaimsHistory(sessions), load_claim))
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(serve())
