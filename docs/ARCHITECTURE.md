# Architecture Overview

## System Architecture

The AAN system provides two entry points: a **legacy Intercom webhook** and a
**platform-agnostic REST API** (`integrations/conversations.py`) for direct
integration without Intercom.

```
         Clients
    ┌──────────┴──────────┐
    │                     │
    ▼                     ▼
POST /api/webhook    POST /api/conversations
(Intercom legacy)    (REST API, any client)
         │
         └──────────┬──────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │       LangGraph Orchestrator      │
    │                                   │
    │  Custom Answers → Supervisor      │
    │       ↓               ↓           │
    │  (fast-path)    Specialist Agents │
    │                       ↓           │
    │                  Verifier         │
    │                       ↓           │
    │                  Escalator        │
    └────────┬──────────────┬──────────┘
             │              │
             ▼              ▼
        Cosmos DB       Azure OpenAI
        (state)         (GPT-4o/mini)
                            │
                            ▼
                    Azure AI Search (RAG)
```

## Core Components

### 1. Orchestrator Layer
- **Custom Answers** (`orchestrator/custom_answers.py`): Fast-path override layer — checks user message against `agents/custom_answers.yaml` *before* any LLM call; matches skip the entire pipeline
- **Supervisor** (`orchestrator/supervisor.py`): Topic classification using GPT-4o-mini for cost-effective routing
- **Verifier** (`orchestrator/verifier.py`): Confidence scoring and grounding checks
- **Escalator** (`orchestrator/escalator.py`): Human handoff with structured context preservation

### 2. Specialist Agents
Each specialist agent is a self-contained LangGraph subgraph:
- **Billing Agent**: Stripe integration, subscription management
- **Tech Agent**: Jira integration, documentation search
- **Returns Agent**: Shopify integration, return policy enforcement

### 3. Integration Layer
- **Conversations REST API** (`integrations/conversations.py`): Platform-agnostic FastAPI app; adds `X-Request-ID` to every response for distributed trace correlation; wraps LLM calls with OpenTelemetry `Timer`
- **Intercom** (`integrations/intercom.py`): Legacy webhook receiver + reply API (HMAC signature validation)
- **External Tools**: Stripe, Jira, Shopify APIs

### 4. Shared Infrastructure
- **Config** (`shared/config.py`): Pydantic `BaseSettings`; reads from env vars and Azure Key Vault
- **Memory** (`shared/memory.py`): Cosmos DB state with lazy connection; 7-day TTL (GDPR)
- **RAG** (`shared/rag.py`): Azure AI Search hybrid search
- **Telemetry** (`shared/telemetry.py`): Azure Monitor OpenTelemetry wrapper; graceful no-op when `APPINSIGHTS_CONNECTION_STRING` is absent; provides `configure_telemetry()`, `track_event()`, `track_metric()`, `get_logger()`, and `Timer` context manager

### 5. Data Layer
- **Cosmos DB**: Conversation state, agent registry (7-day TTL for GDPR)
- **Azure AI Search**: Vector store for RAG with hybrid search
- **Key Vault**: Secure secret management

## Data Flow

1. **User sends message** — via REST API (`POST /conversations`) or Intercom webhook
2. **Custom answers checked** — if a pattern matches `agents/custom_answers.yaml`, reply immediately (no LLM)
3. **Supervisor classifies** query → determines topic (billing / returns / tech / general)
4. **Specialist agent executes** — retrieves RAG context, calls external tools, generates response
5. **Verifier checks** response → computes confidence score (0–1)
6. **Decision point**:
   - **High confidence** (≥ 0.7) → return response to caller
   - **Low confidence** (< 0.7) → Escalator generates structured handoff summary
7. **State persisted** → Cosmos DB (7-day TTL)
8. **Telemetry emitted** → Application Insights (events + latency metrics via `shared/telemetry.py`)

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

- **Application Insights** (`shared/telemetry.py`): Custom event tracking (`track_event`) and latency metrics (`Timer`, `track_metric`). Wire up by setting `APPINSIGHTS_CONNECTION_STRING`. All calls no-op silently when the env var is absent.
- **Distributed tracing**: Every HTTP response includes `X-Request-ID` (propagated from caller or auto-generated) for cross-service correlation
- **LangSmith** (optional): Set `LANGCHAIN_TRACING_V2=true` for detailed agent trace logs
- **Azure Monitor**: Alerts on escalation rate, p95 latency, failure rate
