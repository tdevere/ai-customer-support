"""
Supervisor node for topic classification and routing.
"""
from typing import Dict, Any, List
import yaml
from pathlib import Path
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from shared.config import settings


class TopicClassifier:
    """Classifies user queries into topic categories for routing."""
    
    def __init__(self):
        """Initialize classifier with cheap model for cost efficiency."""
        self.llm = AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            deployment_name=settings.azure_openai_deployment_gpt4_mini,
            temperature=0.0
        )
        
        # Load agent registry
        registry_path = Path(__file__).parent.parent / "agents" / "registry.yaml"
        with open(registry_path, 'r') as f:
            self.registry = yaml.safe_load(f)['registry']
    
    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classify query into one or more topics.
        
        Args:
            query: User query
            
        Returns:
            Dict with topics list and confidence scores
        """
        # Build topic descriptions
        topics_desc = []
        for topic, config in self.registry.items():
            if config.get('enabled', False):
                keywords = ", ".join(config.get('keywords', []))
                topics_desc.append(
                    f"- {topic}: {config['description']} (keywords: {keywords})"
                )
        
        topics_text = "\n".join(topics_desc)
        
        system_prompt = f"""You are a topic classifier for a customer support system.
Your job is to classify customer queries into one or more of these topics:

{topics_text}

Analyze the query and return:
1. The primary topic (most relevant)
2. Any secondary topics (if the query touches multiple areas)
3. A confidence score (0.0 to 1.0) for each topic

Format your response as:
PRIMARY: topic_name (confidence)
SECONDARY: topic_name (confidence), topic_name (confidence)

If no topic matches well, use:
PRIMARY: general (0.5)"""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Customer query: {query}")
        ]
        
        response = self.llm.invoke(messages)
        result = self._parse_classification(response.content)
        
        return result
    
    def _parse_classification(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM classification response."""
        result = {
            "primary_topic": "general",
            "primary_confidence": 0.5,
            "secondary_topics": [],
            "all_topics": []
        }
        
        lines = response_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith("PRIMARY:"):
                # Extract topic and confidence
                parts = line.replace("PRIMARY:", "").strip()
                if "(" in parts:
                    topic = parts.split("(")[0].strip()
                    try:
                        conf = float(parts.split("(")[1].replace(")", "").strip())
                    except:
                        conf = 0.5
                    result["primary_topic"] = topic
                    result["primary_confidence"] = conf
                    result["all_topics"].append({"topic": topic, "confidence": conf})
            
            elif line.startswith("SECONDARY:"):
                # Extract secondary topics
                parts = line.replace("SECONDARY:", "").strip()
                for topic_part in parts.split(","):
                    topic_part = topic_part.strip()
                    if "(" in topic_part:
                        topic = topic_part.split("(")[0].strip()
                        try:
                            conf = float(topic_part.split("(")[1].replace(")", "").strip())
                        except:
                            conf = 0.3
                        result["secondary_topics"].append(topic)
                        result["all_topics"].append({"topic": topic, "confidence": conf})
        
        return result
    
    def get_agent_configs(self, topics: List[str]) -> List[Dict[str, Any]]:
        """
        Get agent configurations for given topics.
        
        Args:
            topics: List of topic names
            
        Returns:
            List of agent configurations
        """
        configs = []
        for topic in topics:
            if topic in self.registry and self.registry[topic].get('enabled', False):
                configs.append({
                    "topic": topic,
                    **self.registry[topic]
                })
        return configs


# Global classifier instance
classifier = TopicClassifier()
