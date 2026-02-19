"""
Unit tests for RAGKnowledgeBase (shared/rag.py).

Azure Search and OpenAI embedding calls are fully mocked.
"""

import pytest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_search_result(
    doc_id: str,
    content: str,
    title: str = "Test Doc",
    topic: str = "billing",
    url: str = "",
    score: float = 0.9,
) -> dict:
    """Build a minimal dict that looks like an Azure Search result."""
    return {
        "id": doc_id,
        "content": content,
        "title": title,
        "topic": topic,
        "url": url,
        "metadata": {},
        "@search.score": score,
    }


def _patched_rag(mocker):
    """
    Return a RAGKnowledgeBase whose internal Azure clients are mocked.
    Also patches settings so _ensure_connected succeeds.
    """
    from shared.config import settings

    mocker.patch.object(
        settings, "azure_search_endpoint", "https://test.search.windows.net"
    )
    mocker.patch.object(settings, "azure_search_key", "test-key-123")
    mocker.patch.object(
        settings, "azure_openai_endpoint", "https://test.openai.azure.com"
    )
    mocker.patch.object(settings, "azure_openai_api_key", "test-oai-key")

    mock_search_client = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 1536

    mocker.patch("shared.rag.SearchClient", return_value=mock_search_client)
    mocker.patch("shared.rag.AzureOpenAIEmbeddings", return_value=mock_embeddings)

    from shared.rag import RAGKnowledgeBase

    kb = RAGKnowledgeBase(index_name="test-index")
    return kb, mock_search_client, mock_embeddings


# ---------------------------------------------------------------------------
# Lazy initialisation
# ---------------------------------------------------------------------------


def test_lazy_init_no_clients_before_first_use():
    """Creating a RAGKnowledgeBase must not connect to Azure on __init__."""
    from shared.rag import RAGKnowledgeBase

    kb = RAGKnowledgeBase()
    assert kb._search_client is None
    assert kb._embeddings is None


def test_ensure_connected_creates_clients(mocker):
    kb, mock_sc, mock_emb = _patched_rag(mocker)
    # Accessing the property triggers _ensure_connected
    _ = kb.search_client
    assert kb._search_client is not None
    assert kb._embeddings is not None


def test_ensure_connected_only_calls_once(mocker):
    kb, _, _ = _patched_rag(mocker)
    _ = kb.search_client
    _ = kb.search_client
    _ = kb.embeddings
    # SearchClient constructor only called once despite multiple property accesses
    from shared import rag as rag_module

    assert rag_module.SearchClient.call_count == 1  # type: ignore[attr-defined]


def test_ensure_connected_raises_without_config():
    """_ensure_connected raises RuntimeError if search credentials are missing."""
    from shared.config import settings
    from shared.rag import RAGKnowledgeBase
    import unittest.mock as mock_lib

    with (
        mock_lib.patch.object(settings, "azure_search_endpoint", ""),
        mock_lib.patch.object(settings, "azure_search_key", ""),
    ):
        kb = RAGKnowledgeBase()
        with pytest.raises(RuntimeError, match="not configured"):
            _ = kb.search_client


# ---------------------------------------------------------------------------
# retrieve_context
# ---------------------------------------------------------------------------


def test_retrieve_context_hybrid_search(mocker):
    """Hybrid search (default) calls search_client.search with text + vector."""
    kb, mock_sc, _ = _patched_rag(mocker)

    docs = [_make_search_result("doc1", "How to pay your invoice")]
    mock_sc.search.return_value = iter(docs)

    result = kb.retrieve_context("how to pay", topic="billing", top_k=3)

    mock_sc.search.assert_called_once()
    call_kwargs = mock_sc.search.call_args[1]
    assert call_kwargs["search_text"] == "how to pay"
    assert len(result) == 1
    assert result[0]["content"] == "How to pay your invoice"


def test_retrieve_context_vector_only(mocker):
    """Passing use_hybrid=False sends search_text=None."""
    kb, mock_sc, _ = _patched_rag(mocker)
    mock_sc.search.return_value = iter([])

    kb.retrieve_context("password reset", use_hybrid=False)

    call_kwargs = mock_sc.search.call_args[1]
    assert call_kwargs["search_text"] is None


def test_retrieve_context_applies_topic_filter(mocker):
    kb, mock_sc, _ = _patched_rag(mocker)
    mock_sc.search.return_value = iter([])

    kb.retrieve_context("reset password", topic="technical")

    call_kwargs = mock_sc.search.call_args[1]
    assert call_kwargs["filter"] == "topic eq 'technical'"


def test_retrieve_context_no_topic_filter(mocker):
    kb, mock_sc, _ = _patched_rag(mocker)
    mock_sc.search.return_value = iter([])

    kb.retrieve_context("anything")

    call_kwargs = mock_sc.search.call_args[1]
    assert call_kwargs["filter"] is None


def test_retrieve_context_returns_empty_list_on_exception(mocker):
    kb, mock_sc, _ = _patched_rag(mocker)
    mock_sc.search.side_effect = RuntimeError("search unavailable")

    result = kb.retrieve_context("crash query")

    assert result == []


def test_retrieve_context_result_shape(mocker):
    """Each returned item has the expected keys."""
    kb, mock_sc, _ = _patched_rag(mocker)
    mock_sc.search.return_value = iter(
        [_make_search_result("d1", "content here", title="My Title", topic="returns")]
    )

    result = kb.retrieve_context("anything")

    assert result[0]["id"] == "d1"
    assert result[0]["title"] == "My Title"
    assert result[0]["topic"] == "returns"
    assert result[0]["score"] == 0.9


# ---------------------------------------------------------------------------
# format_context_for_prompt
# ---------------------------------------------------------------------------


def test_format_context_for_prompt_empty():
    from shared.rag import RAGKnowledgeBase

    kb = RAGKnowledgeBase()
    assert kb.format_context_for_prompt([]) == "No relevant context found."


def test_format_context_for_prompt_includes_source_numbers():
    from shared.rag import RAGKnowledgeBase

    kb = RAGKnowledgeBase()
    docs = [
        {
            "title": "Invoice FAQ",
            "url": "https://help.example.com/invoice",
            "content": "Pay online.",
        },
        {"title": "", "url": "", "content": "Another doc."},
    ]
    result = kb.format_context_for_prompt(docs)

    assert "[Source 1]" in result
    assert "[Source 2]" in result
    assert "Invoice FAQ" in result
    assert "Pay online." in result
    assert "Another doc." in result


def test_format_context_for_prompt_skips_empty_url():
    from shared.rag import RAGKnowledgeBase

    kb = RAGKnowledgeBase()
    docs = [{"title": "T", "url": "", "content": "C"}]
    result = kb.format_context_for_prompt(docs)

    assert "URL:" not in result


# ---------------------------------------------------------------------------
# add_document
# ---------------------------------------------------------------------------


def test_add_document_uploads_and_returns_id(mocker):
    kb, mock_sc, mock_emb = _patched_rag(mocker)
    mock_emb.embed_query.return_value = [0.5] * 1536

    doc_id = kb.add_document(
        content="How to reset your password.",
        title="Password Reset Guide",
        topic="technical",
        url="https://help.example.com/password",
    )

    assert doc_id == "technical_password_reset_guide"
    mock_sc.upload_documents.assert_called_once()
    uploaded = mock_sc.upload_documents.call_args[1]["documents"][0]
    assert uploaded["content"] == "How to reset your password."
    assert uploaded["topic"] == "technical"


def test_add_document_raises_on_upload_error(mocker):
    kb, mock_sc, _ = _patched_rag(mocker)
    mock_sc.upload_documents.side_effect = RuntimeError("upload failed")

    with pytest.raises(RuntimeError, match="upload failed"):
        kb.add_document("content", "title", "topic")
