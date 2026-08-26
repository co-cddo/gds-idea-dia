"""Tests for dia.agent.mcp.tools.athena — Athena SQL MCP tools."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from dia.agent.mcp.tools import athena
from dia.agent.mcp.tools.athena import check_sql_safety

# --- check_sql_safety ---

_FORBIDDEN = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "GRANT", "REVOKE"]


def test_check_sql_safety_allows_plain_select():
    check_sql_safety("SELECT * FROM some_table LIMIT 10")  # should not raise


@pytest.mark.parametrize("keyword", _FORBIDDEN)
def test_check_sql_safety_blocks_forbidden_keywords(keyword):
    with pytest.raises(ValueError, match="Only SELECT statements are allowed."):
        check_sql_safety(f"SELECT * FROM x; {keyword} TABLE x")


def test_check_sql_safety_is_case_insensitive():
    with pytest.raises(ValueError):
        check_sql_safety("drop table x")


def test_check_sql_safety_does_not_false_positive_on_substring():
    """'UPDATED_AT' contains 'UPDATE' as a substring but isn't the keyword —
    the space-padded match should not flag it."""
    check_sql_safety("SELECT updated_at FROM some_table")  # should not raise


def test_check_sql_safety_strips_whitespace_before_checking():
    check_sql_safety("   SELECT 1   ")  # should not raise


# --- list_athena_tables ---


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_list_athena_tables_returns_sorted_names_per_db(mock_wr, mock_get_session):
    mock_wr.catalog.get_tables.return_value = [{"Name": "b_table"}, {"Name": "a_table"}]

    result = athena.list_athena_tables()

    assert '"a_table"' in result
    assert '"b_table"' in result
    # called once per database
    assert mock_wr.catalog.get_tables.call_count == 3


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_list_athena_tables_passes_boto3_session(mock_wr, mock_get_session):
    mock_wr.catalog.get_tables.return_value = []
    mock_get_session.return_value = "fake-session"

    athena.list_athena_tables()

    _, kwargs = mock_wr.catalog.get_tables.call_args
    assert kwargs["boto3_session"] == "fake-session"


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_list_athena_tables_isolates_per_db_errors(mock_wr, mock_get_session):
    """One database raising an exception shouldn't affect the others — each db's
    entry becomes an error message string instead of raising."""
    mock_wr.catalog.get_tables.side_effect = [
        [{"Name": "ok_table"}],
        Exception("boom"),
        [{"Name": "another_table"}],
    ]

    result = athena.list_athena_tables()

    assert "ok_table" in result
    assert "Error: boom" in result
    assert "another_table" in result


# --- get_table_schema ---


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_get_table_schema_returns_column_types(mock_wr, mock_get_session):
    mock_wr.catalog.get_table_types.return_value = {"col_a": "string", "col_b": "bigint"}

    result = athena.get_table_schema("assurance_contracts", "extracted_contracts")

    assert "col_a" in result
    assert "string" in result


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_get_table_schema_strips_quotes_from_table_name(mock_wr, mock_get_session):
    mock_wr.catalog.get_table_types.return_value = {}

    athena.get_table_schema("db", '"quoted_table"')

    _, kwargs = mock_wr.catalog.get_table_types.call_args
    assert kwargs["table"] == "quoted_table"


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_get_table_schema_returns_error_string_on_exception(mock_wr, mock_get_session):
    mock_wr.catalog.get_table_types.side_effect = Exception("no such table")

    result = athena.get_table_schema("db", "table")

    assert result == "Error: no such table"


# --- execute_sql ---


def test_execute_sql_rejects_unsafe_sql_before_calling_aws():
    with patch("dia.agent.mcp.tools.athena.wr") as mock_wr:
        with pytest.raises(ValueError):
            athena.execute_sql("assurance_contracts", "DROP TABLE x")
        mock_wr.athena.read_sql_query.assert_not_called()


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_execute_sql_uses_contracts_workgroup_for_contracts_db(mock_wr, mock_get_session):
    mock_wr.athena.read_sql_query.return_value = pd.DataFrame()

    athena.execute_sql(athena.settings.contracts_db, "SELECT 1")

    _, kwargs = mock_wr.athena.read_sql_query.call_args
    assert kwargs["workgroup"] == athena.settings.contracts_workgroup


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_execute_sql_uses_gats_workgroup_for_other_dbs(mock_wr, mock_get_session):
    mock_wr.athena.read_sql_query.return_value = pd.DataFrame()

    athena.execute_sql(athena.settings.gats_service_db, "SELECT 1")

    _, kwargs = mock_wr.athena.read_sql_query.call_args
    assert kwargs["workgroup"] == athena.settings.gats_workgroup


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_execute_sql_returns_zero_rows_message_for_empty_dataframe(mock_wr, mock_get_session):
    mock_wr.athena.read_sql_query.return_value = pd.DataFrame()

    result = athena.execute_sql("assurance_contracts", "SELECT 1")

    assert result == "Query returned 0 rows."


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_execute_sql_returns_dataframe_as_string_when_non_empty(mock_wr, mock_get_session):
    mock_wr.athena.read_sql_query.return_value = pd.DataFrame({"col": [1, 2]})

    result = athena.execute_sql("assurance_contracts", "SELECT col FROM t")

    assert "col" in result
    assert "1" in result


@patch("dia.agent.mcp.tools.athena.get_session")
@patch("dia.agent.mcp.tools.athena.wr")
def test_execute_sql_returns_error_string_on_exception(mock_wr, mock_get_session):
    mock_wr.athena.read_sql_query.side_effect = Exception("timeout")

    result = athena.execute_sql("assurance_contracts", "SELECT 1")

    assert result == "Query error: timeout"


# --- register ---


def test_register_attaches_all_three_tools_to_server():
    mock_server = MagicMock()
    mock_tool_decorator = MagicMock()
    mock_server.tool.return_value = mock_tool_decorator

    athena.register(mock_server)

    assert mock_server.tool.call_count == 3
    mock_tool_decorator.assert_any_call(athena.list_athena_tables)
    mock_tool_decorator.assert_any_call(athena.get_table_schema)
    mock_tool_decorator.assert_any_call(athena.execute_sql)
