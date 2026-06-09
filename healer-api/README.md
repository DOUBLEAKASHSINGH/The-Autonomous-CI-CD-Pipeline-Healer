# The Autonomous CI/CD Pipeline Healer

An automated pipeline debugging tool integrating **n8n** and **FastAPI + LangGraph**. It intercepts CI webhook failures, routes them to a multi-agent reasoning backend that analyzes stack traces, writes a code patch, and autonomously opens a Pull Request — all without human intervention until the review stage.

---

## Architecture

```
GitHub CI fails
      │  webhook
      ▼
┌─────────────────────────┐        ┌──────────────────────────────────────┐
│       n8n Workflow      │        │         Python FastAPI + LangGraph   │
│                         │        │                                      │
│  1. Webhook trigger     │        │  Agent 1 — Diagnostician             │
│  2. Fetch error logs    │──POST──▶  ↓ structured diagnosis JSON         │
│  3. Fetch code diff     │        │  Agent 2 — Coder                     │
│  4. Call /diagnose      │◀─JSON──│  ↓ patched file                      │
│  5. Create branch + PR  │        │  Agent 3 — Evaluator                 │
│  6. Slack alert         │        │  ↓ PASS → return   RETRY → loop      │
└─────────────────────────┘        └──────────────────────────────────────┘
```

---

## Project Structure

```
healer-api/
├── main.py                     # FastAPI entry point  (/diagnose endpoint)
├── graph.py                    # LangGraph state machine (3-agent cyclic graph)
├── models.py                   # Pydantic request/response schemas
├── agents/
│   ├── diagnostician.py        # Agent 1: extracts diagnosis from stack trace
│   ├── coder.py                # Agent 2: writes the code patch
│   └── evaluator.py            # Agent 3: validates patch → PASS or RETRY
├── .github/workflows/ci.yml    # GitHub Actions: triggers healer on failure
├── render.yaml                 # One-click Render deployment config
├── requirements.txt
└── .env.example
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/DOUBLEAKASHSINGH/The-Autonomous-CI-CD-Pipeline-Healer.git
cd The-Autonomous-CI-CD-Pipeline-Healer
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and GITHUB_TOKEN
```

### 3. Run locally

```bash
uvicorn main:app --reload
# API docs: http://localhost:8000/docs
```

### 4. Test with a sample payload

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "error_log": "TypeError: can only concatenate str (not int) to str\n  File app/utils.py, line 14, in format_output\n    return name + age",
    "code_diff": "--- a/app/utils.py\n+++ b/app/utils.py\n@@ -12,7 +12,7 @@\n-    return name + str(age)\n+    return name + age",
    "repo": "DOUBLEAKASHSINGH/The-Autonomous-CI-CD-Pipeline-Healer",
    "file_path": "app/utils.py"
  }'
```

---

## Deployment (Render)

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New Web Service** → connect this repo.
3. Render auto-detects `render.yaml`.
4. In the Render dashboard, set **Environment Variables**:
   - `ANTHROPIC_API_KEY` = your Anthropic key
   - `GITHUB_TOKEN` = a GitHub PAT with `repo` + `workflow` scopes
5. Copy your live Render URL (e.g. `https://cicd-pipeline-healer.onrender.com`).

---

## n8n Workflow Setup

### Node sequence

| # | Node type | What it does |
|---|-----------|-------------|
| 1 | **Webhook** | Receives POST from GitHub Actions |
| 2 | **HTTP Request** | `GET /repos/{repo}/actions/runs/{run_id}/logs` — downloads error log ZIP |
| 3 | **HTTP Request** | `GET /repos/{repo}/commits/{sha}` (diff) |
| 4 | **HTTP Request** | `POST https://your-app.onrender.com/diagnose` — calls AI backend |
| 5 | **GitHub** node | Creates new branch `ai-fix/{run_id}` |
| 6 | **GitHub** node | Commits patched file to that branch |
| 7 | **GitHub** node | Opens Pull Request → main |
| 8 | **Slack** node | Sends developer alert with PR link |

### n8n credentials needed

- **GitHub OAuth2** or Personal Access Token (`repo`, `workflow` scopes)
- **Slack Webhook URL** (from your Slack app settings)

### Important: Log extraction

The GitHub Actions log endpoint returns a ZIP file. Add a **Code** node after the log fetch to extract the text:

```javascript
// n8n Code node (JavaScript)
const Buffer = require('buffer').Buffer;
const JSZip = require('jszip');

const zipBuffer = Buffer.from($input.first().binary.data.data, 'base64');
const zip = await JSZip.loadAsync(zipBuffer);
const files = Object.keys(zip.files);
let logText = '';
for (const name of files) {
  logText += await zip.files[name].async('string');
}
// Trim to last 6000 chars to stay within token limits
return [{ json: { log_text: logText.slice(-6000) } }];
```

---

## GitHub Secrets Required

In your repo → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `N8N_WEBHOOK_URL` | Your n8n webhook test/production URL |

---

## How the Agent Loop Works

```
error_log + code_diff
        │
        ▼
  ┌──────────────┐
  │ Diagnostician│  → { file_path, error_line, error_type, root_cause }
  └──────────────┘
        │
        ▼
  ┌──────────────┐
  │    Coder     │  → full corrected file (plain text, no markdown)
  └──────────────┘
        │
        ▼
  ┌──────────────┐
  │  Evaluator   │  → { verdict: "PASS"|"RETRY", reason: "..." }
  └──────────────┘
        │
   PASS │ RETRY (up to 3×)
        │    └──────────────► back to Coder
        ▼
   return to n8n
```

The `MAX_ITERATIONS = 3` guard in `graph.py` ensures the loop always terminates.

---

## API Reference

### `POST /diagnose`

**Request body:**
```json
{
  "error_log": "raw stack trace string",
  "code_diff": "unified diff string",
  "repo": "owner/repo-name",
  "commit_sha": "abc123",
  "file_path": "optional/path/to/file.py"
}
```

**Response:**
```json
{
  "file_path": "app/utils.py",
  "patched_file": "...full corrected file content...",
  "diagnosis": {
    "file_path": "app/utils.py",
    "error_line": 14,
    "error_type": "TypeError",
    "root_cause": "...",
    "language": "python"
  },
  "verdict": "PASS",
  "reason": "The patch converts age to str before concatenation, directly addressing the root cause.",
  "iterations": 1
}
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | [n8n](https://n8n.io) |
| API framework | [FastAPI](https://fastapi.tiangolo.com) |
| Agent framework | [LangGraph](https://langchain-ai.github.io/langgraph/) |
| LLM | [Anthropic Claude Sonnet 4](https://anthropic.com) |
| Deployment | [Render](https://render.com) |
| CI integration | GitHub Actions |
| Notifications | Slack / Microsoft Teams |

---

## License

MIT
