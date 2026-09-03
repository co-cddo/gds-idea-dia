"""Tests for dia.agent.models — AgentInput and AgentResponse."""

from datetime import date

import pytest
from pydantic import ValidationError

from dia.agent.models import AgentInput, AgentResponse


# --- AgentInput ---


def test_agent_input_creates_with_all_fields():
    agent_input = AgentInput(query="what is the risk?", department="Home Office")

    assert agent_input.query == "what is the risk?"
    assert agent_input.department == "Home Office"


def test_agent_input_is_frozen():
    agent_input = AgentInput(query="what is the risk?", department="Home Office")

    with pytest.raises(ValidationError):
        agent_input.query = "a different question"


def test_agent_input_requires_query_and_department():
    with pytest.raises(ValidationError):
        AgentInput(query="what is the risk?")

    with pytest.raises(ValidationError):
        AgentInput(department="Home Office")


# --- AgentResponse ---


def test_agent_response_creates_with_all_fields():
    response = AgentResponse(
        department="Home Office",
        query="what is the risk?",
        output="an answer",
    )

    assert response.department == "Home Office"
    assert response.query == "what is the risk?"
    assert response.output == "an answer"


def test_agent_response_generates_id_and_run_date_by_default():
    response = AgentResponse(
        department="Home Office",
        query="what is the risk?",
        output="an answer",
    )

    assert isinstance(response.id, str) and response.id != ""
    assert response.run_date == date.today()


def test_agent_response_ids_are_unique_per_instance():
    first = AgentResponse(department="Home Office", query="q", output="a")
    second = AgentResponse(department="Home Office", query="q", output="a")

    assert first.id != second.id


def test_agent_response_is_frozen():
    response = AgentResponse(department="Home Office", query="q", output="a")

    with pytest.raises(ValidationError):
        response.output = "a different answer"


def test_agent_response_requires_department_query_and_output():
    with pytest.raises(ValidationError):
        AgentResponse(query="q", output="a")

    with pytest.raises(ValidationError):
        AgentResponse(department="Home Office", output="a")

    with pytest.raises(ValidationError):
        AgentResponse(department="Home Office", query="q")
