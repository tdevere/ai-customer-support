"""
RAG (Retrieval Augmented Generation) implementation using Azure AI Search.
Provides context retrieval for specialist agents.
"""

from typing import List, Dict, Any, Optional
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from langchain_openai import AzureOpenAIEmbeddings
from shared.config import settings


class RAGKnowledgeBase:
    """
    Manages knowledge retrieval using Azure AI Search with hybrid search.
    """

    def __init__(self, index_name: Optional[str] = None):
        """
        Initialize RAG knowledge base.

        Args:
            index_name: Azure Search index name (defaults to settings)
        """
        self.index_name = index_name or settings.azure_search_index

        # Initialize Azure Search client
        self.search_client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(settings.azure_search_key),
        )

        # Initialize embeddings for vector search
        self.embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            model="text-embedding-ada-002",
        )

    def retrieve_context(
        self,
        query: str,
        topic: Optional[str] = None,
        top_k: int = 5,
        use_hybrid: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a query.

        Args:
            query: User query or question
            topic: Optional topic filter (e.g., "billing", "tech")
            top_k: Number of results to return
            use_hybrid: Use hybrid (semantic + vector) search

        Returns:
            List of relevant documents with content and metadata
        """
        try:
            # Generate query embedding for vector search
            query_embedding = self.embeddings.embed_query(query)

            # Build search parameters
            vector_query = VectorizedQuery(
                vector=query_embedding,
                k_nearest_neighbors=top_k,
                fields="content_vector",
            )

            # Add topic filter if specified
            filter_expression = f"topic eq '{topic}'" if topic else None

            # Perform search
            if use_hybrid:
                # Hybrid search (semantic + vector)
                results = self.search_client.search(
                    search_text=query,
                    vector_queries=[vector_query],
                    filter=filter_expression,
                    top=top_k,
                    select=["id", "content", "title", "topic", "url", "metadata"],
                )
            else:
                # Vector-only search
                results = self.search_client.search(
                    search_text=None,
                    vector_queries=[vector_query],
                    filter=filter_expression,
                    top=top_k,
                    select=["id", "content", "title", "topic", "url", "metadata"],
                )

            # Format results
            documents = []
            for result in results:
                documents.append(
                    {
                        "id": result.get("id"),
                        "content": result.get("content", ""),
                        "title": result.get("title", ""),
                        "topic": result.get("topic", ""),
                        "url": result.get("url", ""),
                        "metadata": result.get("metadata", {}),
                        "score": result.get("@search.score", 0),
                    }
                )

            return documents

        except Exception as e:
            print(f"Error retrieving context: {e}")
            return []

    def format_context_for_prompt(self, documents: List[Dict[str, Any]]) -> str:
        """
        Format retrieved documents into a context string for LLM prompt.

        Args:
            documents: List of retrieved documents

        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant context found."

        context_parts = []
        for i, doc in enumerate(documents, 1):
            context_parts.append(f"[Source {i}]")
            if doc.get("title"):
                context_parts.append(f"Title: {doc['title']}")
            if doc.get("url"):
                context_parts.append(f"URL: {doc['url']}")
            context_parts.append(f"Content: {doc['content']}\n")

        return "\n".join(context_parts)

    def add_document(
        self,
        content: str,
        title: str,
        topic: str,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a new document to the knowledge base.

        Args:
            content: Document content
            title: Document title
            topic: Topic category
            url: Optional source URL
            metadata: Optional additional metadata

        Returns:
            Document ID
        """
        try:
            # Generate embedding
            content_vector = self.embeddings.embed_query(content)

            # Create document
            doc_id = f"{topic}_{title.lower().replace(' ', '_')}"
            document = {
                "id": doc_id,
                "content": content,
                "content_vector": content_vector,
                "title": title,
                "topic": topic,
                "url": url,
                "metadata": metadata or {},
            }

            # Upload to search index
            self.search_client.upload_documents(documents=[document])
            return doc_id

        except Exception as e:
            print(f"Error adding document: {e}")
            raise


# Global RAG instance
rag = RAGKnowledgeBase()
