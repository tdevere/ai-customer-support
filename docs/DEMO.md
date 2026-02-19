# Local Demo Guide

Run the full Customer Support API end-to-end — **no Azure credentials required**.  
Every Azure dependency (OpenAI, Cosmos DB, AI Search) is mocked locally.

---

## Quick Start

**Terminal 1** — start the mock server (keep running):

```powershell
.venv\Scripts\python.exe scripts/demo_local.py
```

**Terminal 2** — run the guided demo:

```powershell
.\scripts\demo.ps1
```

Or launch the server automatically:

```powershell
.\scripts\demo.ps1 -StartServer
```

Then open the interactive Swagger UI:

```
http://localhost:8000/docs
```

---

## How It Works

`scripts/demo_local.py` starts the FastAPI app with three layers of mocking:

| Layer | Real component | Mock replacement |
|---|---|---|
| LLM calls | Azure OpenAI (GPT-4o / GPT-4o-mini) | Keyword-routing in `_mock_run_orchestrator()` |
| State persistence | Azure Cosmos DB | In-memory Python dict (`_memory_store`) |
| Knowledge retrieval | Azure AI Search | Hard-coded KB snippets |
| Telemetry | Azure Application Insights | No-op (no connection string) |

The real `integrations/conversations.py` FastAPI app is served unchanged — only the
orchestrator entry-point and the storage singletons are patched at runtime.  
This means every middleware, request model, response shape, and routing rule is
exercised exactly as in production.

---

## Demo Scenarios

The demo script runs four scripted scenes:

| Scene | Customer message | Agent routed | Key outcome |
|---|---|---|---|
| 0 | — | — | Health check confirms API is live |
| 1 | "I was charged twice this month" | `billing` | Invoice details + refund offer |
| 2 | "Thanks, all sorted now" | `billing` (follow-up) | `resolution_state: resolved_confirmed` |
| 3 | "App crashes on login, iPhone iOS 18" | `tech` | Step-by-step troubleshooting guide |
| 4 | `GET /conversations/{id}` | — | State persisted across turns via GET |

---

## Recorded Demo Run

The following output was captured on **2026-02-19** from a clean run of `.\scripts\demo.ps1`.

```
════════════════════════════════════════════════════════════════
  AI Customer Support  —  Adaptive Agent Network  (v1.0)
════════════════════════════════════════════════════════════════
  All Azure services are MOCKED.  No cloud credentials needed.
  Swagger UI  →  http://localhost:8000/docs

────────────────────────────────────────────────────────────────
  SCENE 0  Health check — is the API alive?
────────────────────────────────────────────────────────────────

  REQUEST:
    GET /health

  RESPONSE:
  Status:              ok
  Version:             1.0.0

────────────────────────────────────────────────────────────────
  SCENE 1  Customer reports an unexpected charge on their invoice
────────────────────────────────────────────────────────────────

  REQUEST:
    POST /conversations
    {"message":"Hi, I just noticed I was charged twice on my account this month.
     Can you help me sort this out?","user_id":"user-demo-001"}

  RESPONSE:
  Conversation ID:     51de2a90-6093-4bc1-a238-9eb900048e4d
  Topic detected:      billing
  Confidence:          88%
  Resolution state:    resolved_assumed

Thank you for contacting us about your billing concern.

I've pulled up your account and can see your billing history. Your most recent
invoice was processed on **February 1, 2026** for **$49.00**. If you believe
there's a discrepancy, I can open a billing dispute immediately — refunds are
typically credited back within **5–7 business days**.

Would you like me to initiate a dispute? Or if you can share the specific charge
reference, I can look into it in more detail right now.

────────────────────────────────────────────────────────────────
  SCENE 2  Same conversation — customer confirms the issue is resolved
────────────────────────────────────────────────────────────────

  REQUEST:
    POST /conversations/51de2a90-6093-4bc1-a238-9eb900048e4d/messages
    {"message":"That makes sense, thanks! All sorted now."}

  RESPONSE:
  Resolution state:    resolved_confirmed

  ✔  'resolved_confirmed' — the agent detected a thank-you and closed the loop.

You're welcome! Really glad that sorted things out. If anything else comes up,
we're always here — just message us. Have a great day! 🎉

────────────────────────────────────────────────────────────────
  SCENE 3  Different customer — mobile app crashes on login (iOS)
────────────────────────────────────────────────────────────────

  REQUEST:
    POST /conversations
    {"message":"The app keeps crashing every time I try to log in. I'm on an
     iPhone running iOS 18.","user_id":"user-demo-002"}

  RESPONSE:
  Conversation ID:     7a0b21e4-6e44-4442-82bd-e7da7d6322bb
  Topic detected:      tech
  Confidence:          88%

I'm sorry you're running into this — let's get it fixed.

**Try these steps first:**
1. Force-close the app completely and reopen it
2. Go to **Settings → Advanced → Clear Cache**
3. Make sure you're on the latest version (**v4.2.1** — available in your app store)
4. If the issue persists, uninstall and reinstall the app

I've also checked our status page — **no active incidents** are reported right now.
If none of the above works, reply here with your device model and OS version and
I'll escalate to our engineering team straight away.

────────────────────────────────────────────────────────────────
  SCENE 4  Retrieve conversation history via GET (state persisted across turns)
────────────────────────────────────────────────────────────────

  REQUEST:
    GET /conversations/51de2a90-6093-4bc1-a238-9eb900048e4d

  RESPONSE:
  Status:              success
  Resolution:          resolved_confirmed
  Confidence:          88%

════════════════════════════════════════════════════════════════
  Demo complete  ✔
════════════════════════════════════════════════════════════════
  What just happened in 4 scenes:

  Scene 0  Health check — API is live and responsive
  Scene 1  Billing query → billing agent → structured response
  Scene 2  Follow-up 'thanks' → resolution_state = resolved_confirmed
  Scene 3  New user, tech issue → tech agent → step-by-step fix
  Scene 4  GET /conversations confirms state persisted across turns

  Key capabilities demonstrated:
  • Multi-turn conversation context (Cosmos DB, mocked here)
  • Automatic topic routing  (billing / tech / returns / general)
  • Resolution tracking  (in_progress → resolved_confirmed)
  • X-Request-ID tracing on every response
  • OpenTelemetry telemetry  (no-op when App Insights not set)
  • Zero Azure credentials required for local development

  Swagger UI  →  http://localhost:8000/docs
════════════════════════════════════════════════════════════════
```

---

## Exercising the API Manually

Once the server is running you can also drive it directly with PowerShell:

### Health check

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### Start a conversation

```powershell
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/conversations" `
  -ContentType "application/json" `
  -Body '{"message":"I want to return my order","user_id":"demo-user"}'
```

### Follow-up message

```powershell
# Replace {id} with the conversation_id from the previous response
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/conversations/{id}/messages" `
  -ContentType "application/json" `
  -Body '{"message":"My tracking number is TRK-9982"}'
```

### Retrieve conversation state

```powershell
Invoke-RestMethod http://localhost:8000/conversations/{id}
```

### Or use curl

```bash
# Health
curl http://localhost:8000/health

# New conversation
curl -X POST http://localhost:8000/conversations \
     -H "Content-Type: application/json" \
     -d '{"message":"My invoice looks wrong","user_id":"demo-u1"}'

# Follow-up (replace CONV_ID)
curl -X POST http://localhost:8000/conversations/CONV_ID/messages \
     -H "Content-Type: application/json" \
     -d '{"message":"Thanks, that fixed it!"}'
```

---

## Supported Topic Keywords

The mock orchestrator uses simple keyword matching to route messages.
In production, routing is performed by the GPT-4o-mini topic classifier.

| Topic | Trigger keywords |
|---|---|
| `billing` | charge, invoice, payment, billing, refund, subscription, billed, cost, price, fee |
| `tech` | crash, error, bug, broken, not working, freezes, won't load, login, sign in, slow, app |
| `returns` | return, shipping, delivery, track, tracking, order, package, arrived, missing |
| `general` | *(everything else)* |

---

## Connecting to Real Azure Services

When you are ready to move beyond the mock, fill in `local.settings.json`
with real values (use `local.settings.json.example` as the template):

```json
{
  "Values": {
    "AZURE_OPENAI_ENDPOINT": "https://<your-resource>.openai.azure.com/",
    "AZURE_OPENAI_API_KEY": "<your-key>",
    "COSMOS_ENDPOINT": "https://<your-account>.documents.azure.com:443/",
    "COSMOS_KEY": "<your-key>",
    "AZURE_SEARCH_ENDPOINT": "https://<your-service>.search.windows.net",
    "AZURE_SEARCH_KEY": "<your-admin-key>"
  }
}
```

Then start the Functions host instead of the mock server:

```bash
func start
```

See [DEPLOYMENT.md](./DEPLOYMENT.md) for the full production deployment guide.
