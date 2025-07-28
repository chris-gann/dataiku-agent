# Product Requirements Document (PRD)

**Project:** *Dataiku Agent* — internal Slack AI assistant POC  
**Author:** Chris Gannon  
**Date:** July 25, 2025  
**Status:** Draft / Ready for Dev

---

## 1. Purpose & Vision

Build a **Slack‑native** assistant that answers questions about Dataiku by combining:

1. **Brave Search API** for fresh web results.  
2. **OpenAI o3** for synthesis and conversational tone (now available with advanced reasoning capabilities).  
3. **Slack’s “AI Apps & Assistants”** surfaces (split‑view threads, suggested prompts, typing status, etc.).

**Why?** Prove we can deliver accurate, up‑to‑date answers from public sources inside Slack, ready to layer in Dataiku‑specific APIs later.

---

## 2. Goals & Non‑Goals

| Goals (MVP) | Non‑Goals (later) |
|---|---|
| ✅ Run in Chris’s dev workspace only | Marketplace listing / security review |
| ✅ Respond to plain‑English questions about Dataiku | Billing, seat management, OAuth with Dataiku |
| ✅ Use AI‑app UX (assistant threads, status, suggested prompts) | Slack Workflow Builder steps, App Home dashboards |
| ✅ Handle basic errors gracefully | Fine‑tuning or RAG with private docs |

**Success metric:** `/dataiku` (or AI thread) returns a relevant answer in **< 5 s** for **95%** of requests.

---

## 3. User Stories (internal testers)

1. **As a Data Scientist**, I can ask “How do I build a visual recipe in Dataiku?” and get a concise answer with sources.  
2. **As a Maintainer**, I can see the bot “thinking…” while it fetches Brave results.  
3. **As an Admin**, I can install the app to another private channel via the normal “Add apps” dialog.

---

## 4. Functional Requirements

| ID | Description | Priority |
|---|---|---|
| **F‑1** | App responds inside an **AI‑assistant thread** to any user message. | Must |
| **F‑2** | On each message, call **Brave Search API** (`GET /search?q=…`) — top 10 results, JSON. | Must |
| **F‑3** | Build a prompt: `system:` “You are a helpful Dataiku expert…”, add the 10 snippets, add user question → call **OpenAI o3** (`/v1/chat/completions`). | Must |
| **F‑4** | Stream answer back to the Slack thread using `chat.postMessage`. | Must |
| **F‑5** | While waiting, set status **“Searching the web…”** via `assistant.threads.setStatus`. | Must |
| **F‑6** | After answer, clear status and show permalinks of Brave results as footnotes (max 3). | Should |
| **F‑7** | Provide 3 **Suggested prompts** (“How to schedule a scenario?”, “What is a recipe?”, “Where to find plugins?”) via `assistant.threads.setSuggestedPrompts`. | Should |
| **F‑8** | Log each request/latency to console for debugging. | Must |
| **F‑9** | Graceful error replies if Brave quota or OpenAI errors. | Must |

---

## 5. Non‑Functional Requirements

- **Latency:** < 5 s p95 (includes Brave + OpenAI).  
- **Security:** tokens loaded from `.env`, never logged.  
- **Scalability:** single user; run locally with Socket Mode; no autoscale.  
- **Observability:** basic timestamped logs.

---

## 6. Technical Architecture

| Layer | Choice |
|---|---|
| **Framework** | **Bolt‑Python 2.x** (`Assistant` class) — supports new AI events. |
| **Transport** | **Socket Mode** (WebSocket) for local dev; avoids public URL. |
| **Hosting** | Local machine or Codespace + `slack run` (Slack CLI) for hot‑reload. |
| **Secrets** | `.env` — `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `OPENAI_API_KEY`, `BRAVE_API_KEY`. |
| **Libraries** | `python-dotenv`, `openai==0.28`, `requests`, `slack_bolt`, `slack_sdk`. |
| **Repo layout** |  |

```
dataiku-agent/
├─ manifest.yml         # Slack app config
├─ .env.example         # token placeholders
├─ src/
│  └─ app.py            # Bolt entry point
├─ requirements.txt
└─ README.md
```

### 6.1 Slack manifest (minimal)

```yaml
_display_information:
  name: Dataiku Agent
features:
  ai_app: true               # enable AI surfaces
oauth_config:
  bot_scopes:
    - assistant:write        # setStatus, suggested prompts
    - chat:write
    - im:history
settings:
  event_subscriptions:
    bot_events:
      - assistant_thread_started
      - assistant_thread_context_changed
```

---

## 7. APIs

| API | Endpoint | Key storage | Notes |
|---|---|---|---|
| **Brave Search** | `GET https://api.search.brave.com/res/v1/web/search` | `.env` → `BRAVE_API_KEY` | params: `q`, `count=10`, `source=web`, `ai=true` |
| **OpenAI o3** | `POST https://api.openai.com/v1/chat/completions` | `.env` | model `o3`, temperature `0.3` |
| **Slack** | `assistant.threads.*`, `chat.postMessage` | Bot token | Rate limit ~20 requests/sec per workspace |

---

## 8. Flow Sequence

1. **Event:** `assistant_thread_started` → set suggested prompts (F‑7).  
2. **Event:** message inside thread:  
   1. `setStatus("Searching the web…")` (F‑5).  
   2. Call **Brave** → parse JSON → keep **title, snippet, URL**.  
   3. Build messages → call **OpenAI o3** → stream response.  
   4. `chat.postMessage` with answer + **top 3 sources**.  
   5. **Clear status**.  
3. **Logging:** record question and total latency.

---

## 9. Error Handling

| Scenario | Behavior |
|---|---|
| Brave quota hit | Reply: “Search quota exceeded, please try later.” |
| OpenAI error | Reply: “LLM unavailable, retry later.” |
| Slack rate limit | Exponential backoff using the `Retry-After` header. |
| Missing tokens | Abort on startup with descriptive console error. |

---

## 10. Testing Plan

- **Unit** — mock Brave JSON and OpenAI response.  
- **Integration** — real Brave & OpenAI calls with dummy tokens.  
- **Slack functional** — install in dev workspace, verify:  
  - Suggested prompts visible.  
  - Status message appears & clears.  
  - Response includes hyperlinks.  
- **Load** — 20 rapid queries → ensure no 429 errors.  
- **Security** — scan logs for token leakage.

---

## 11. Open Issues

- Confirm Brave Search free‑tier limits.  
- Decide **streaming vs single-shot** response (streaming adds complexity).  
- Tidy up **source formatting** (Markdown list vs footnotes).

---

## 12. Timeline (aggressive)

| Date | Milestone |
|---|---|
| **Day 0** | Repo scaffold + manifest validated |
| **Day 1** | Brave & OpenAI helper functions with unit tests |
| **Day 2** | Slack event plumbing; Socket Mode working |
| **Day 3** | Suggested prompts + status; functional tests pass |
| **Day 4** | Error handling + logging |
| **Day 5** | Docs & demo video |

---

## 13. Deliverables

- Git repo **`dataiku-agent`**.  
- **README.md** with setup steps.  
- **60‑sec video demo** (Loom/Teams) showing ask → answer → sources.  
- This **PRD** in repo root as `PRD.md`.

---

## 14. Approval

| Role | Name | Sign‑off |
|---|---|---|
| Product Owner | Chris Gannon | ☐ |
| Dev Lead | (TBD) | ☐ |
| Stakeholder | (Mentor / Manager) | ☐ |

---

*End of document*
