# AVARIX

**Avarix** is an AI-assisted technical research chatbot that searches a local knowledge base first, uses AeroCalc for explicit aerospace calculations, and falls back to web search when the local database cannot answer the question.

> **Personal project · current stable line: v10.x**

## Core pipeline

```text
                         ┌─────────────────────┐
                         │       USER          │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │ Query Understanding │
                         │ intent + entities   │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │   KNOWLEDGE BASE    │
                         │                     │
                         │ concepts            │
                         │ formulas            │
                         │ problems            │
                         │ worked solutions    │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │  KB RESULT ANALYSIS │
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
              ↓                     ↓                      ↓
       Exact solution       Similar problem        No useful DB
       exists               exists                 solution
              │                     │                      │
              ↓                     ↓                      ↓
       Return DB solution    Extract method +      AeroCalc /
                            variables/formula       MathEngine
                                    │                      │
                                    └──────────┬───────────┘
                                               ↓
                                      Computation result
                                               ↓
                                      Combine with DB
                                      explanation/method
                                               ↓
                                      Final AVARIX answer
```

**Every question is independent. Intellex does not use previous chat messages as hidden context for retrieval or answering.**

Features

- PDF, DOCX, PPTX, XLSX, TXT, Markdown and CSV ingestion.
- BM25 + ChromaDB retrieval.
- Database-first answer routing.
- Relevance filtering to reduce false database matches.
- Sentence-fragment protection for badly split document chunks.
- AeroCalc integration for explicit numerical aerospace calculations.
- Web-search fallback.
- OpenRouter support for higher-quality answer generation.
- Ollama/OpenAI support remains available through environment variables.
- Free extractive fallback when no LLM key is configured.
- MathJax rendering for engineering equations.
- Expandable database and web source cards.
- Responsive desktop/mobile UI.
- Server-side API-key handling.
- Basic server-side rate limiting for public deployments.

Repository structure

```text
Avarix/
├── app/
│   ├── main.py
│   ├── chatbot.py
│   ├── llm.py
│   ├── knowledge_base.py
│   ├── vector_store.py
│   ├── embeddings.py
│   ├── web_search.py
│   ├── aerocalc_bridge.py
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
│
├── aerocalc/
│   ├── core.py
│   ├── compressible.py
│   ├── numeric.py
│   ├── physics.py
│   ├── references.py
│   └── modules/
│
├── cache/
│   ├── index.pkl
│   └── chroma/
│
├── .env.example
├── .gitignore
├── requirements.txt
└── run_web.py
```

The separate React/Vite frontend and standalone AeroCalc web server are intentionally not included. Avarix uses one FastAPI process and one static UI, which makes the repository smaller and easier to deploy.

## Setup

### 1. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the API key

Copy:

```text
.env.example
```

to:

```text
.env
```

Then put the real key in `.env`:

```env
OPENROUTER_API_KEY=your_real_key_here
```

**Never put the real key in Python, JavaScript, HTML, or GitHub source files.**

### 4. Start Avarix

```bash
python run_web.py
```

Open:

```text
http://127.0.0.1:8000
```

## 🔐 API-key security

The API key is intentionally read only by the Python backend:

```python
os.getenv("OPENROUTER_API_KEY")
```

The browser communicates only with:

```text
POST /api/chat
```

The key is never returned to the browser and is never inserted into the frontend JavaScript.

### Important

If a real API key was ever committed to GitHub, **do not simply delete the line and reuse the key**. Revoke/rotate that key at the provider first, then remove the old secret from Git history.

The repository includes:

```text
.gitignore
```

with:

```text
.env
```

so the local secret file is not accidentally committed.

### Public deployment

Hiding the key protects it from being copied by visitors, but a public backend can still be abused: someone could repeatedly call `/api/chat` and make your server spend your API credits.

Intellex therefore includes lightweight server-side controls:

- per-client chat rate limit
- rebuild cooldown
- provider keys remain server-side

For a serious public deployment, also use a reverse proxy/WAF and provider-side spending limits.

## Knowledge base

The distributed `cache/` contains the current prebuilt index.

To create a new knowledge base, place source documents in:

```text
data/
```

and rebuild the index:

```text
POST /api/rebuild
```

or use the **Rebuild Index** button in the UI.

Supported source formats include:

```text
.pdf
.docx
.pptx
.xlsx
.txt
.md
.csv
```

Images can also be processed when the optional OCR dependencies are available.

## Answer routing

Avarix deliberately avoids letting AeroCalc hijack ordinary questions.

For example:

```text
What is Mach number?
```

is treated as a knowledge question.

Whereas:

```text
Calculate the speed of sound at 11,000 m.
```

can be routed to AeroCalc if the database does not contain a sufficiently relevant answer.

The intended priority is:

**Database → AeroCalc for genuine calculations → Web**

## Source presentation

Answers are displayed first.

Sources are separated into expandable cards:

```text
📚 Database sources  5  ⌄
🌐 Web sources       5  ⌄
```

This keeps raw retrieval snippets from overwhelming the actual answer.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Intellex UI |
| `/api/health` | GET | Backend/index status |
| `/api/chat` | POST | Ask an independent question |
| `/api/rebuild` | POST | Rebuild the local index |

Example:

```json
{
  "message": "What is Mach number?"
}
```

## Deployment

For local development:

```text
Browser → localhost:8000 → FastAPI → Avarix
```

For a hosted deployment:

```text
Browser
   │
   ▼
HTTPS / reverse proxy
   │
   ▼
FastAPI
   ├── local knowledge index
   ├── AeroCalc
   ├── LLM provider
   └── web search
```

GitHub stores the **source code**; it does not execute the Python backend.

## Notes

This is a personal research/development project. AI-generated answers and engineering calculations should be independently verified before being used for safety-critical or formal engineering decisions.


### Web-search note
The OpenRouter API key is used for answer generation. It is not automatically treated as a web-search engine. Web search uses DuckDuckGo by default, or Tavily/Exa/SerpAPI when configured; OpenRouter web search is opt-in via `WEB_SEARCH_BACKEND=openrouter`. Search results are relevance-filtered before being shown to the user.
