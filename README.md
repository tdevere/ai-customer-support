# Adaptive Agent Network (AAN) Customer Support System

[![CI/CD](https://github.com/tdevere/ai-customer-support/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/tdevere/ai-customer-support/actions/workflows/ci-cd.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-ready, plug-and-play **Adaptive Agent Network (AAN)** that augments **Intercom + Fin AI Agent** for specialized customer support. This system handles 70-80% of simple queries automatically via Fin, with AAN activating for topic-specialist needs, low-confidence outputs, or complex multi-topic cases.

## 🚀 Features

- **Multi-Agent Architecture**: Dynamic topic routing to specialized agents (Billing, Technical, Returns)
- **Intelligent Routing**: Automatic classification and routing based on query content
- **Confidence-Based Escalation**: Smart handoff to human agents when confidence < 70%
- **Intercom Integration**: Seamless webhook and data connector support
- **RAG Knowledge Base**: Azure AI Search-powered context retrieval
- **GDPR Compliant**: 7-day TTL on conversation data, minimal PII storage
- **Serverless Azure**: Fully managed infrastructure with auto-scaling
- **Plug-and-Play Agents**: Add new specialist agents in <1 hour via config

## 📋 Architecture

```mermaid
graph TD
    A[User Query → Intercom] --> B[Fin AI Triage]
    B -->|Simple| C[Fin Replies Directly]
    B -->|Complex| D[AAN Orchestrator]
    D --> E[Topic Classifier]
    E --> F{Route to Specialists}
    F --> G1[Billing Agent]
    F --> G2[Tech Agent]
    F --> G3[Returns Agent]
    G1 & G2 & G3 --> H[Verifier Agent]
    H -->|High Confidence| I[Post Reply to Intercom]
    H -->|Low Confidence| J[Escalate to Human]
```

## 🛠️ Tech Stack

- **Orchestration**: LangGraph + LangChain
- **Backend**: Python 3.11 + Azure Functions
- **LLMs**: Azure OpenAI (GPT-4o, GPT-4o-mini)
- **Vector DB**: Azure AI Search
- **State Management**: Azure Cosmos DB
- **External Tools**: Stripe, Jira, Shopify APIs
- **Monitoring**: Azure Application Insights + LangSmith
- **IaC**: Terraform

## 📦 Project Structure

```
aan-intercom-support/
├── .github/workflows/     # CI/CD pipelines
├── agents/                # Specialist agents
│   ├── billing_agent.py
│   ├── tech_agent.py
│   ├── returns_agent.py
│   └── registry.yaml      # Agent configurations
├── orchestrator/          # Main orchestration logic
│   ├── graph.py          # LangGraph workflow
│   ├── supervisor.py     # Topic classifier
│   ├── verifier.py       # Confidence scorer
│   └── escalator.py      # Human handoff
├── integrations/          # External service integrations
│   ├── intercom.py       # Webhook handler
│   └── tools/            # Stripe, Jira, Shopify tools
├── shared/                # Shared utilities
│   ├── config.py         # Configuration management
│   ├── memory.py         # State persistence
│   └── rag.py            # RAG knowledge base
├── tests/                 # Comprehensive tests
├── infra/                 # Terraform infrastructure
└── requirements.txt       # Python dependencies
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Azure subscription
- Terraform 1.0+
- Azure CLI
- Intercom workspace

### 1. Clone Repository

```bash
git clone https://github.com/tdevere/ai-customer-support.git
cd ai-customer-support
```

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file:

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key

# Azure Cosmos DB
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_KEY=your-search-key

# Intercom
INTERCOM_ACCESS_TOKEN=your-intercom-token
INTERCOM_WEBHOOK_SECRET=your-webhook-secret

# External Services (optional)
STRIPE_API_KEY=your-stripe-key
JIRA_API_TOKEN=your-jira-token
JIRA_BASE_URL=https://your-company.atlassian.net
SHOPIFY_API_KEY=your-shopify-key
SHOPIFY_SHOP_URL=https://your-shop.myshopify.com
```

### 4. Deploy Infrastructure

```bash
cd infra
terraform init
terraform plan -var="environment=dev"
terraform apply -var="environment=dev"
```

### 5. Deploy Function App

```bash
func azure functionapp publish func-aan-support-dev
```

### 6. Configure Intercom Webhook

1. Go to Intercom Settings → Webhooks
2. Add webhook URL: `https://your-function-app.azurewebsites.net/api/webhook`
3. Subscribe to: `conversation.user.replied`, `conversation.user.created`
4. Copy webhook secret to `.env`

## 🧪 Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run with Coverage

```bash
pytest tests/ --cov=. --cov-report=html
```

### Run Specific Test

```bash
pytest tests/test_supervisor.py -v
```

## 📝 Usage

### Adding a New Specialist Agent

1. **Create Agent File**: `agents/new_agent.py`

```python
from typing import Dict, Any, List
from typing_extensions import TypedDict
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, END

class NewAgentState(TypedDict):
    query: str
    response: str
    confidence: float

def create_new_agent():
    # Define your agent logic
    workflow = StateGraph(NewAgentState)
    # Add nodes and edges
    return workflow.compile()

new_agent = create_new_agent()
```

2. **Update Registry**: `agents/registry.yaml`

```yaml
new_topic:
  name: "New Specialist"
  description: "Handles new topic queries"
  module: "agents.new_agent"
  agent_name: "new_agent"
  enabled: true
  tools:
    - tool_name_1
    - tool_name_2
  keywords:
    - keyword1
    - keyword2
```

3. **Deploy**: The agent is now available in <1 hour!

### Manual Testing

```python
from orchestrator.graph import run_aan_orchestrator

result = await run_aan_orchestrator(
    conversation_id="test-123",
    user_id="user-456",
    message="How do I cancel my subscription?",
    context={"customer_id": "cust_789"}
)

print(result)
```

## 📊 Monitoring

### Application Insights

Access metrics at: Azure Portal → Application Insights

Key metrics:
- Request duration (target: <8s p95)
- Escalation rate (target: <10%)
- Success rate (target: >90%)
- Cost per query (target: <$0.05)

### LangSmith (Optional)

Set `LANGCHAIN_TRACING_V2=true` and configure API key for detailed trace logs.

## 💰 Cost Estimates

For 1,000 queries/day with 50% routed to AAN:

| Service | Monthly Cost |
|---------|--------------|
| Azure Functions | $5-10 |
| Azure OpenAI | $40-60 |
| Cosmos DB | $25 |
| Azure AI Search | $75 |
| Storage & KV | $2 |
| **Total** | **~$150** |

## 🔒 Security

- Managed Identity for Azure resource access
- All secrets stored in Azure Key Vault
- Webhook signature validation
- GDPR-compliant TTL (7 days)
- Encryption at rest and in transit

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- Powered by [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
- Integrated with [Intercom](https://www.intercom.com/)

## 📧 Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/tdevere/ai-customer-support/issues)
- Email: support@example.com

---

**Built with ❤️ for scalable, intelligent customer support**