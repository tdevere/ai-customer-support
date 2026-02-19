"""
Unit tests for ConversationMemory (shared/memory.py).

All Cosmos DB calls are mocked — no real Azure services required.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from azure.cosmos.exceptions import CosmosHttpResponseError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosmos_404():
    """Build a CosmosHttpResponseError that looks like a 404."""
    err = CosmosHttpResponseError.__new__(CosmosHttpResponseError)
    err.status_code = 404
    err.message = "Not Found"
    return err


def _cosmos_500():
    err = CosmosHttpResponseError.__new__(CosmosHttpResponseError)
    err.status_code = 500
    err.message = "Internal Server Error"
    return err


def _make_mock_cosmos():
    """
    Return a fully-mocked CosmosClient + mock container.
    Returns (mock_client_class, mock_state_container).
    """
    mock_state_container = MagicMock()
    mock_registry_container = MagicMock()

    mock_database = MagicMock()
    mock_database.create_container_if_not_exists.side_effect = [
        mock_state_container,
        mock_registry_container,
    ]

    mock_client = MagicMock()
    mock_client.create_database_if_not_exists.return_value = mock_database

    mock_client_class = MagicMock(return_value=mock_client)

    return mock_client_class, mock_state_container, mock_registry_container


# ---------------------------------------------------------------------------
# Lazy initialisation
# ---------------------------------------------------------------------------


def test_lazy_init_no_cosmos_on_import():
    """Importing shared.memory must not make any real Cosmos calls."""
    import shared.memory as m

    # The global instance should exist but not be connected yet
    assert m.memory._client is None


def test_lazy_init_connects_on_first_use(mocker):
    """_ensure_connected() is called once on the first operation and not again."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    assert mem._client is None  # not connected yet

    # First access via property triggers connection
    _ = mem.state_container
    assert mem._client is not None
    mock_cls.assert_called_once()

    # Second access must NOT call CosmosClient again
    _ = mem.state_container
    mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# save_state
# ---------------------------------------------------------------------------


def test_save_state_upserts_document(mocker):
    """save_state calls upsert_item with correct document shape."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    mem.save_state("conv-123", {"status": "success", "message": "ok"})

    mock_state_cont.upsert_item.assert_called_once()
    doc = mock_state_cont.upsert_item.call_args[0][0]
    assert doc["id"] == "conv-123"
    assert doc["conversation_id"] == "conv-123"
    assert doc["state"]["status"] == "success"
    assert "updated_at" in doc


def test_save_state_raises_on_cosmos_error(mocker):
    """save_state re-raises CosmosHttpResponseError from upsert_item."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_state_cont.upsert_item.side_effect = _cosmos_500()

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    with pytest.raises(CosmosHttpResponseError):
        mem.save_state("conv-err", {"status": "error"})


# ---------------------------------------------------------------------------
# load_state / get_state
# ---------------------------------------------------------------------------


def test_load_state_returns_state(mocker):
    """load_state returns the state dict stored inside the Cosmos document."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_state_cont.read_item.return_value = {
        "id": "conv-abc",
        "state": {"status": "success", "message": "hello"},
    }

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    result = mem.load_state("conv-abc")

    assert result == {"status": "success", "message": "hello"}
    mock_state_cont.read_item.assert_called_once_with(
        item="conv-abc", partition_key="conv-abc"
    )


def test_load_state_returns_none_on_404(mocker):
    """load_state returns None (not raises) when the document does not exist."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_state_cont.read_item.side_effect = _cosmos_404()

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    result = mem.load_state("does-not-exist")

    assert result is None


def test_get_state_is_alias_for_load_state(mocker):
    """get_state and load_state return the same value for the same conversation."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_state_cont.read_item.return_value = {"id": "c1", "state": {"x": 1}}

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    assert mem.get_state("c1") == mem.load_state("c1")


def test_load_state_raises_on_non_404_cosmos_error(mocker):
    """load_state propagates non-404 Cosmos errors to the caller."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_state_cont.read_item.side_effect = _cosmos_500()

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    with pytest.raises(CosmosHttpResponseError):
        mem.load_state("conv-err")


# ---------------------------------------------------------------------------
# delete_state
# ---------------------------------------------------------------------------


def test_delete_state_calls_delete_item(mocker):
    """delete_state calls delete_item with the correct partition key."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    mem.delete_state("conv-delete-me")

    mock_state_cont.delete_item.assert_called_once_with(
        item="conv-delete-me", partition_key="conv-delete-me"
    )


def test_delete_state_silently_ignores_404(mocker):
    """delete_state does not raise when document is already gone (idempotent)."""
    mock_cls, mock_state_cont, _ = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_state_cont.delete_item.side_effect = _cosmos_404()

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    mem.delete_state("already-gone")  # must not raise


# ---------------------------------------------------------------------------
# register_agent / list_agents / get_agent_config
# ---------------------------------------------------------------------------


def test_register_agent_upserts_document(mocker):
    """register_agent upserts a document in the registry container."""
    mock_cls, _, mock_reg_cont = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    mem.register_agent(
        "billing", {"name": "Billing Agent", "description": "handles billing"}
    )

    mock_reg_cont.upsert_item.assert_called_once()
    doc = mock_reg_cont.upsert_item.call_args[0][0]
    assert doc["id"] == "billing"
    assert doc["topic"] == "billing"
    assert doc["name"] == "Billing Agent"


def test_get_agent_config_returns_doc(mocker):
    """get_agent_config returns the registry document for a topic."""
    mock_cls, _, mock_reg_cont = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_reg_cont.read_item.return_value = {"id": "billing", "topic": "billing"}

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    result = mem.get_agent_config("billing")

    assert result["topic"] == "billing"


def test_get_agent_config_returns_none_on_404(mocker):
    """get_agent_config returns None when the topic is not registered."""
    mock_cls, _, mock_reg_cont = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_reg_cont.read_item.side_effect = _cosmos_404()

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    result = mem.get_agent_config("unknown_topic")

    assert result is None


def test_list_agents_returns_list(mocker):
    """list_agents queries the registry and returns a list of configs."""
    mock_cls, _, mock_reg_cont = _make_mock_cosmos()
    mocker.patch("shared.memory.CosmosClient", mock_cls)
    mock_reg_cont.query_items.return_value = iter(
        [{"id": "billing"}, {"id": "technical"}]
    )

    from shared.memory import ConversationMemory

    mem = ConversationMemory()
    agents = mem.list_agents()

    assert len(agents) == 2
    assert agents[0]["id"] == "billing"
