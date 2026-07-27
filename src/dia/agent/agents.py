"""Model/agent factories: make_model(), make_agent(), per-prompt factories."""


def make_model(
    *,
    model_id: str = RESPONSE_MODEL_ID,
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
        region_name=AWS_REGION,
        max_tokens=max_tokens,
        additional_request_fields=additional_request_fields,
    )


def _make_mcp_client(url: Optional[str] = None) -> MCPClient:
    """Build an MCPClient pointing at the running server."""
    target = url or server_url()

    def _transport():
        return streamablehttp_client(target)

    return MCPClient(_transport)


def make_agent(
    system_prompt: str,
    *,
    model: Optional[BedrockModel] = None,
    mcp_client: Optional[MCPClient] = None,
    callback_handler: Optional[Any] = None,
    server_url_override: Optional[str] = None,
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


# Per-prompt convenience factories. Each one builds a fresh agent so callers can
# parameterise prompts (e.g. department name) without sharing state.
def make_default_agent(department_name: str = "Home Office", **kwargs: Any) -> Agent:
    return make_agent(get_default_system_prompt(department_name), **kwargs)


def make_dbr_agent(department_name: str = "Home Office", **kwargs: Any) -> Agent:
    return make_agent(get_dbr_system_prompt(department_name), **kwargs)


def make_gats_query_agent(**kwargs: Any) -> Agent:
    return make_agent(get_gats_query_system_prompt(), **kwargs)


def make_project_investigation_agent(**kwargs: Any) -> Agent:
    return make_agent(get_project_investigation_system_prompt(), **kwargs)


def make_supplier_lockin_agent(department_name: str = "", **kwargs: Any) -> Agent:
    return make_agent(get_supplier_lockin_system_prompt(department_name), **kwargs)


def make_supplier_ecosystem_agent(department_name: str = "", **kwargs: Any) -> Agent:
    return make_agent(get_supplier_ecosystem_system_prompt(department_name), **kwargs)


def make_targeted_question_agent(**kwargs: Any) -> Agent:
    return make_agent(get_targeted_question_system_prompt(), **kwargs)


def make_sovereign_stack_agent(**kwargs: Any) -> Agent:
    return make_agent(get_sovereign_stack_system_prompt_v3(), **kwargs)


def make_graph_cost_aware_agent(**kwargs: Any) -> Agent:
    return make_agent(get_graph_cost_aware_system_prompt(), **kwargs)


def make_pitch_deck_agent(**kwargs: Any) -> Agent:
    return make_agent(get_pitch_deck_system_prompt(), **kwargs)


def make_ai_transformation_agent(department_name: str = "Home Office", **kwargs: Any) -> Agent:
    return make_agent(get_ai_transformation_system_prompt(department_name), **kwargs)


def make_ai_transformation_agent_v2(department_name: str = "Home Office", **kwargs: Any) -> Agent:
    return make_agent(get_ai_transformation_system_prompt_v2(department_name), **kwargs)


def make_all_agents(
    department_name: str = "Home Office",
    *,
    model: Optional[BedrockModel] = None,
    callback_handler: Optional[Any] = None,
) -> SimpleNamespace:
    """Build the common set of agents in one call.

    Returns a SimpleNamespace with attributes:
      .default, .dbr, .gats_query, .project, .supplier_lockin, .supplier_ecosystem,
      .targeted_question, .sovereign_stack, .graph_cost_aware, .pitch_deck,
      .ai_transformation

    A single shared model + MCPClient is used across all agents to avoid spinning
    up duplicate connections.
    """
    if model is None:
        model = make_model()
    mcp_client = _make_mcp_client()

    common: Dict[str, Any] = {
        "model": model,
        "mcp_client": mcp_client,
        "callback_handler": callback_handler,
    }

    return SimpleNamespace(
        default=make_default_agent(department_name, **common),
        dbr=make_dbr_agent(department_name, **common),
        gats_query=make_gats_query_agent(**common),
        project=make_project_investigation_agent(**common),
        supplier_lockin=make_supplier_lockin_agent(department_name, **common),
        supplier_ecosystem=make_supplier_ecosystem_agent(department_name, **common),
        targeted_question=make_targeted_question_agent(**common),
        sovereign_stack=make_sovereign_stack_agent(**common),
        graph_cost_aware=make_graph_cost_aware_agent(**common),
        pitch_deck=make_pitch_deck_agent(**common),
        ai_transformation=make_ai_transformation_agent(department_name, **common),
    )


__all__ = [
    # config
    "AWS_REGION",
    "NEPTUNE_ENDPOINT",
    "AOSS_ENDPOINT",
    "ATHENA_CONTRACTS_DB",
    "ATHENA_CONTRACTS_TABLE",
    "ATHENA_CONTRACTS_WORKGROUP",
    "ATHENA_GATS_DB",
    "ATHENA_GATS_WORKGROUP",
    "ATHENA_GATS_OUTPUT",
    "ATHENA_GATS_SERVICE_DB",
    "ATHENA_GATS_SERVICE_TABLE",
    "KB_IDS",
    "RESPONSE_MODEL_ID",
    "DEFAULT_MCP_PORT",
    "DEFAULT_MCP_URL",
    # stores + server
    "session",
    "graph_store",
    "vector_store",
    "graph_index",
    "mcp_server",
    "tool_parameters",
    "update_tool_params",
    "check_sql_safety",
    # server lifecycle
    "start_server",
    "server_url",
    # tool functions (also exposed for direct use)
    "list_athena_tables",
    "get_table_schema",
    "execute_sql",
    "wait_after_timeout",
    "kb_search_gats_business_cases",
    "kb_search_sr25_bids",
    "kb_search_sr21_bids",
    "kb_search_nao_reports",
    "kb_search_efficiency_reports",
    "web_search_gov",
    # model + agent factories
    "make_model",
    "make_agent",
    "make_default_agent",
    "make_dbr_agent",
    "make_gats_query_agent",
    "make_project_investigation_agent",
    "make_supplier_lockin_agent",
    "make_supplier_ecosystem_agent",
    "make_targeted_question_agent",
    "make_sovereign_stack_agent",
    "make_graph_cost_aware_agent",
    "make_pitch_deck_agent",
    "make_ai_transformation_agent",
    "make_ai_transformation_agent_v2",
    "make_all_agents",
]
