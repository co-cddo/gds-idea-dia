"""Model/agent factory: make_model(), make_agent()."""

from typing import Any

from mcp.client.streamable_http import streamable_http_client
from strands import Agent
from strands.handlers import PrintingCallbackHandler
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient

from dia.agent.config import settings
from dia.agent.mcp.server import server_url
from dia.agent.prompts.templates import (
    get_default_system_prompt,
)


def make_model(
    *,
    model_id: str = settings.model_id,
    max_tokens: int = 20_000,
    temperature: float = 1.0,
    thinking_budget_tokens: int = 8192,
    effort: str = "high",
    thinking_display: str = "summarized",
) -> BedrockModel:
    """Build a BedrockModel with extended thinking enabled by default.

    Handles two different Anthropic thinking APIs on Bedrock:

    - Manual thinking (Claude Sonnet/Opus 4.5/4.6 and earlier 4.x):
      ``thinking = {type: "enabled", budget_tokens: N}``.
    - Adaptive thinking (Claude Sonnet 5, Opus 4.7/4.8, and later): these models
      reject ``type: "enabled"`` with a 400 error. Use
      ``thinking = {type: "adaptive"}`` plus a sibling
      ``output_config = {effort: ...}`` (one of "low" / "medium" / "high" /
      "xhigh" / "max") to control thinking depth.

    Adaptive-thinking models also reject any non-default ``temperature`` /
    ``top_p`` / ``top_k``, so we omit ``temperature`` entirely for those models.
    On those models ``thinking.display`` defaults to "omitted" (empty thinking
    field); we set it to "summarized" so reasoning is still visible.
    """
    # Model families that require the newer adaptive-thinking + effort API and
    # reject manual `type: "enabled"`. Match on the model name portion after any
    # regional / inference-profile prefix (e.g. "eu.anthropic.").
    _adaptive_thinking_models = (
        "claude-sonnet-5",
        "claude-opus-5",
        "claude-opus-4-7",
        "claude-opus-4-8",
    )
    uses_adaptive = any(name in model_id for name in _adaptive_thinking_models)

    if uses_adaptive:
        # NOTE: do NOT send `temperature` — adaptive models 400 on non-default
        # sampling params.
        additional_request_fields: dict = {
            "thinking": {
                "type": "adaptive",
                "display": thinking_display,
            },
            "output_config": {
                "effort": effort,
            },
        }
    else:
        additional_request_fields = {
            "temperature": temperature,
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens,
            },
        }

    return BedrockModel(
        model_id=model_id,
        region_name=settings.aws_region,
        max_tokens=max_tokens,
        additional_request_fields=additional_request_fields,
    )


def _make_mcp_client(url: str | None = None) -> MCPClient:
    """Build an MCPClient pointing at the running server."""
    target = url or server_url()

    def _transport():
        return streamable_http_client(target)

    return MCPClient(_transport)


def make_agent(
    system_prompt: str,
    *,
    model: BedrockModel | None = None,
    mcp_client: MCPClient | None = None,
    callback_handler: Any | None = None,
    server_url_override: str | None = None,
) -> Agent:
    """Build a Strands Agent given a system prompt.

    Args:
        system_prompt: The full system prompt string for the agent.
        model: Optional BedrockModel; defaults to make_model() if not provided.
        mcp_client: Optional MCPClient; defaults to one bound to the running server.
        callback_handler: Optional Strands callback handler; defaults to PrintingCallbackHandler.
        server_url_override: Optional URL to use instead of the running server's URL
            (only consulted if mcp_client is not provided).
    """
    if mcp_client is None:
        mcp_client = _make_mcp_client(server_url_override)
    if model is None:
        model = make_model()
    if callback_handler is None:
        callback_handler = PrintingCallbackHandler()

    return Agent(
        model=model,
        tools=[mcp_client],
        system_prompt=system_prompt,
        callback_handler=callback_handler,
    )


def make_default_agent(department_name: str | None = None, **kwargs: Any) -> Agent:
    return make_agent(get_default_system_prompt(department_name or ""), **kwargs)
