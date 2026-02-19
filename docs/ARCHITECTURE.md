# Architecture Overview

## System Architecture

The AAN system follows a modular, serverless architecture built entirely on Azure:

```
┌─────────────────────────────────────────────────────────┐
│                    Intercom Platform                     │
│                                                          │
│  ┌────────────┐        ┌──────────────┐                │
│  │   Fin AI   │───────▶│   Webhook    │                │
│  │   Agent    │        │  to AAN      │                │
│  └────────────┘        └──────────────┘                │
└─────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────┐
│              Azure Functions (Serverless)                │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │           LangGraph Orchestrator                  │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │  │
│  │  │Classifier│→ │Supervisor│→ │Specialist    │   │  │
│  │  └──────────┘  └──────────┘  │Agents        │   │  │
│  │                               └──────────────┘   │  │
│  │  ┌──────────┐  ┌──────────┐                     │  │
│  │  │ Verifier │→ │Escalator │                     │  │
│  │  └──────────┘  └──────────┘                     │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
          │              │              │
          ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│Azure Cosmos │  │Azure OpenAI  │  │Azure AI      │
│DB (State)   │  │(LLMs)        │  │Search (RAG)  │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Core Components

### 1. Orchestrator Layer
- **Supervisor**: Topic classification and routing
- **Classifier**: Uses GPT-4o-mini for cost-effective classification
- **Verifier**: Confidence scoring and grounding checks
- **Escalator**: Human handoff with context preservation

### 2. Specialist Agents
Each specialist agent is a self-contained LangGraph subgraph:
- **Billing Agent**: Stripe integration, subscription management
- **Tech Agent**: Jira integration, documentation search
- **Returns Agent**: Shopify integration, return policy enforcement

### 3. Data Layer
- **Cosmos DB**: Conversation state, agent registry (7-day TTL for GDPR)
- **Azure AI Search**: Vector store for RAG with hybrid search
- **Key Vault**: Secure secret management

### 4. Integration Layer
- **Intercom**: Webhook receiver + reply API
- **External Tools**: Stripe, Jira, Shopify APIs

## Data Flow

1. **User sends message** → Intercom
2. **Fin evaluates** → Routes to AAN if needed
3. **Webhook received** → Azure Functions
4. **Classifier analyzes** query → Determines topic(s)
5. **Supervisor routes** → Specialist agent(s)
6. **Agents execute**:
   - Retrieve context from RAG
   - Call external tools if needed
   - Generate response
7. **Verifier checks** response → Computes confidence
8. **Decision point**:
   - **High confidence** (≥0.7) → Post reply to Intercom
   - **Low confidence** (<0.7) → Escalate to human
9. **State saved** → Cosmos DB

## Scalability Features

- **Horizontal scaling**: Azure Functions auto-scale
- **Parallel execution**: Multiple agents can run concurrently
- **Caching**: RAG results cached in memory
- **Rate limiting**: Built-in via Azure API Management (optional)

## Security Features

- **Webhook signature validation**: HMAC SHA256
- **Managed Identity**: No credentials in code
- **Encryption**: At rest (Cosmos) and in transit (HTTPS)
- **GDPR compliance**: 7-day TTL, minimal PII storage
- **Secret management**: Azure Key Vault

## Cost Optimization

- **GPT-4o-mini** for classification (cheaper)
- **GPT-4o** for specialist responses (quality)
- **Consumption plan** for Functions (pay-per-use)
- **Session consistency** for Cosmos (lower cost)
- **Basic tier** for AI Search (dev/staging)

## Monitoring & Observability

- **Application Insights**: Request traces, failures, performance
- **Custom metrics**: Escalation rate, confidence scores, cost per query
- **LangSmith** (optional): Detailed agent traces
- **Azure Monitor**: Alerts on anomalies
