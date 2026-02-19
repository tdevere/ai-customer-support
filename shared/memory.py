"""
Shared memory and state management using LangGraph checkpointer and Cosmos DB.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from shared.config import settings


class ConversationMemory:
    """
    Manages conversation state and history using Azure Cosmos DB.
    Provides persistence layer for LangGraph checkpointer.
    """

    def __init__(self):
        """Initialize Cosmos DB client and containers."""
        self.client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        self.database = self.client.create_database_if_not_exists(
            settings.cosmos_database
        )

        # State container for conversation checkpoints
        self.state_container = self.database.create_container_if_not_exists(
            id=settings.cosmos_container_state,
            partition_key=PartitionKey(path="/conversation_id"),
            default_ttl=604800,  # 7 days TTL for GDPR compliance
        )

        # Registry container for agent configurations
        self.registry_container = self.database.create_container_if_not_exists(
            id=settings.cosmos_container_registry,
            partition_key=PartitionKey(path="/topic"),
        )

    def save_state(self, conversation_id: str, state: Dict[str, Any]) -> None:
        """
        Save conversation state to Cosmos DB.

        Args:
            conversation_id: Unique conversation identifier
            state: State dictionary to persist
        """
        document = {
            "id": conversation_id,
            "conversation_id": conversation_id,
            "state": state,
            "updated_at": datetime.utcnow().isoformat(),
            "_ts": int(datetime.utcnow().timestamp()),
        }

        try:
            self.state_container.upsert_item(document)
        except CosmosHttpResponseError as e:
            print(f"Error saving state for {conversation_id}: {e}")
            raise

    def load_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Load conversation state from Cosmos DB.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            State dictionary or None if not found
        """
        try:
            item = self.state_container.read_item(
                item=conversation_id, partition_key=conversation_id
            )
            return item.get("state")
        except CosmosHttpResponseError as e:
            if e.status_code == 404:
                return None
            print(f"Error loading state for {conversation_id}: {e}")
            raise

    def delete_state(self, conversation_id: str) -> None:
        """
        Delete conversation state (for GDPR compliance).

        Args:
            conversation_id: Unique conversation identifier
        """
        try:
            self.state_container.delete_item(
                item=conversation_id, partition_key=conversation_id
            )
        except CosmosHttpResponseError as e:
            if e.status_code != 404:
                print(f"Error deleting state for {conversation_id}: {e}")

    def get_agent_config(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve agent configuration from registry.

        Args:
            topic: Topic name (e.g., "billing", "tech")

        Returns:
            Agent configuration or None if not found
        """
        try:
            item = self.registry_container.read_item(item=topic, partition_key=topic)
            return item
        except CosmosHttpResponseError as e:
            if e.status_code == 404:
                return None
            print(f"Error loading agent config for {topic}: {e}")
            raise

    def register_agent(self, topic: str, config: Dict[str, Any]) -> None:
        """
        Register a new agent in the registry.

        Args:
            topic: Topic name
            config: Agent configuration
        """
        document = {
            "id": topic,
            "topic": topic,
            "name": config.get("name", topic.title()),
            "description": config.get("description", ""),
            "enabled": config.get("enabled", True),
            "tools": config.get("tools", []),
            "rag_index": config.get("rag_index", settings.azure_search_index),
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            self.registry_container.upsert_item(document)
        except CosmosHttpResponseError as e:
            print(f"Error registering agent {topic}: {e}")
            raise

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all registered agents.

        Returns:
            List of agent configurations
        """
        query = "SELECT * FROM c WHERE c.enabled = true"
        items = list(
            self.registry_container.query_items(
                query=query, enable_cross_partition_query=True
            )
        )
        return items

    def add_feedback(self, conversation_id: str, feedback: Dict[str, Any]) -> None:
        """
        Add feedback to conversation for analytics and improvement.

        Args:
            conversation_id: Unique conversation identifier
            feedback: Feedback data (rating, resolution, etc.)
        """
        state = self.load_state(conversation_id)
        if state:
            if "feedback" not in state:
                state["feedback"] = []
            state["feedback"].append(
                {**feedback, "timestamp": datetime.utcnow().isoformat()}
            )
            self.save_state(conversation_id, state)


# Global memory instance
memory = ConversationMemory()
