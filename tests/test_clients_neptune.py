from unittest.mock import MagicMock, patch

from dia.clients.neptune import LocalNeptuneClient, _patched_hosts


@patch("dia.clients.neptune.boto3.Session")
def test_creates_session_with_profile(mock_session_cls):
    """Session is created with the specified profile_name and region."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.client.return_value = MagicMock()

    LocalNeptuneClient(endpoint="my-cluster.eu-west-2.neptune.amazonaws.com", profile_name="my-profile")

    mock_session_cls.assert_called_once_with(profile_name="my-profile", region_name="eu-west-2")


@patch("dia.clients.neptune.boto3.Session")
def test_client_endpoint_url_includes_port(mock_session_cls):
    """The neptunedata client is created with https://{endpoint}:8182 as endpoint_url."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.client.return_value = MagicMock()

    LocalNeptuneClient(endpoint="my-cluster.eu-west-2.neptune.amazonaws.com")

    call_kwargs = mock_session.client.call_args
    assert call_kwargs[1]["endpoint_url"] == "https://my-cluster.eu-west-2.neptune.amazonaws.com:8182"


@patch("dia.clients.neptune.boto3.Session")
def test_query_calls_execute_open_cypher_query(mock_session_cls):
    """query() calls execute_open_cypher_query with the given Cypher string."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_client = MagicMock()
    mock_session.client.return_value = mock_client
    mock_client.execute_open_cypher_query.return_value = {"results": []}

    client = LocalNeptuneClient(endpoint="my-cluster.eu-west-2.neptune.amazonaws.com")
    client.query("MATCH (n) RETURN n LIMIT 5")

    mock_client.execute_open_cypher_query.assert_called_once_with(openCypherQuery="MATCH (n) RETURN n LIMIT 5")


@patch("dia.clients.neptune.boto3.Session")
def test_endpoint_property(mock_session_cls):
    """endpoint property returns the hostname passed at construction."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.client.return_value = MagicMock()

    client = LocalNeptuneClient(endpoint="my-cluster.eu-west-2.neptune.amazonaws.com")

    assert client.endpoint == "my-cluster.eu-west-2.neptune.amazonaws.com"


@patch("dia.clients.neptune.boto3.Session")
def test_registers_endpoint_for_dns_redirection(mock_session_cls):
    """Creating a client registers the endpoint hostname for DNS patching."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.client.return_value = MagicMock()

    endpoint = "test-unique-endpoint.eu-west-2.neptune.amazonaws.com"
    _patched_hosts.discard(endpoint)  # ensure clean state before any assertions

    LocalNeptuneClient(endpoint=endpoint)

    assert endpoint in _patched_hosts
    _patched_hosts.discard(endpoint)
