"""AVARIX FastAPI server.

The web UI is served from app/static. API credentials are server-side only:
the browser never receives OPENROUTER_API_KEY or any other provider key.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
import time

from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.chatbot import ChatBot


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="AVARIX",
    description="Aerospace Intelligence & Knowledge Platform",
)

chatbot = ChatBot()

RATE_LIMIT = max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")))
REBUILD_COOLDOWN = max(
    1,
    int(os.getenv("REBUILD_COOLDOWN_SECONDS", "60")),
)

# Maximum browser-supplied conversation-session identifier.
# This is only for separating conversational memory; it is NOT authentication.
MAX_SESSION_ID_LENGTH = 128

_requests = defaultdict(deque)
_last_rebuild = defaultdict(float)


class ChatRequest(BaseModel):
    question: str
    session_id: str = "default"
    rebuild_index: bool = False


class ChatResponse(BaseModel):
    answer: str
    case: int | None = None
    source: str | None = None
    db_results: list = []
    web_results: list = []
    aerocalc: dict | None = None
    mode: str | None = None
    structured: dict | None = None
    visuals: list = []

    # Existing routing metadata
    case: int | None = None
    source: str | None = None

    # Existing retrieval/calculation data
    db_results: list = []
    web_results: list = []
    aerocalc: dict | None = None

    # Existing provider information
    mode: str | None = None

    # ---------------------------------------------------------------
    # AVARIX structured-answer layer
    # ---------------------------------------------------------------
    #
    # These are optional so the backend remains backward compatible.
    # Older chatbot responses containing only "answer" will still work.
    #
    structured: dict | None = None

    # Optional related visuals for the AVARIX visual panel.
    visuals: list = []


def _client_id(request: Request) -> str:
    # Cloudflare sets this header for proxied requests. Otherwise use the
    # direct socket address. Do not trust arbitrary X-Forwarded-For values.
    cloudflare_ip = request.headers.get("cf-connecting-ip")

    if cloudflare_ip:
        return cloudflare_ip.strip()

    return request.client.host if request.client else "unknown"


def _allowed(client_id: str) -> bool:
    now = time.monotonic()
    q = _requests[client_id]

    while q and now - q[0] > 60:
        q.popleft()

    if len(q) >= RATE_LIMIT:
        return False

    q.append(now)
    return True


@app.on_event("startup")
def _startup():
    chatbot.ensure_index()


@app.get("/")
def index():
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html")
    )


@app.get("/api/health")
def health():
    return JSONResponse({
        "status": "ok",
        **chatbot.stats(),
    })


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = chatbot.answer(
        req.question,
        rebuild_index=req.rebuild_index,
        session_id=req.session_id,
    )

    response_data = {
        "answer": result.get("answer", ""),
        "case": result.get("case"),
        "source": result.get("source"),
        "db_results": result.get("db_results", []),
        "web_results": result.get("web_results", []),
        "aerocalc": result.get("aerocalc"),
        "mode": result.get("mode"),
        "structured": result.get("structured"),
        "visuals": result.get("visuals", []),
    }

    return ChatResponse(**response_data)

    # Keep conversation memory isolated per client + browser session.
    # A missing session_id still gets a stable per-client default session.
    supplied_session = (
        (req.session_id or "").strip()[:MAX_SESSION_ID_LENGTH]
    )

    session_key = (
        f"{client}:{supplied_session}"
        if supplied_session
        else f"{client}:default"
    )

    result = bot.answer(
        req.message,
        rebuild_index=req.rebuild_index,
        session_id=session_key,
    )

    if os.getenv(
        "INTELLEX_PERF_LOG",
        "1",
    ).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        print(
            f"[PERF] HTTP /api/chat TOTAL: "
            f"{time.perf_counter() - t0:.3f}s",
            flush=True,
        )

    # ---------------------------------------------------------------
    # Backward-compatible response normalization
    # ---------------------------------------------------------------
    #
    # ChatBot may eventually return additional AVARIX fields.
    # We explicitly expose only the fields defined by ChatResponse.
    #
    # This prevents an unexpected internal field from breaking the API.
    response_data = {
        "answer": result.get("answer", ""),
        "case": result.get("case"),
        "source": result.get("source"),
        "db_results": result.get("db_results", []),
        "web_results": result.get("web_results", []),
        "aerocalc": result.get("aerocalc"),
        "mode": result.get("mode"),
        "structured": result.get("structured"),
        "visuals": result.get("visuals", []),
    }

    return ChatResponse(**response_data)


@app.post("/api/rebuild")
def rebuild(request: Request):
    client = _client_id(request)
    now = time.monotonic()

    if now - _last_rebuild[client] < REBUILD_COOLDOWN:
        return JSONResponse(
            {
                "error": (
                    "Please wait before rebuilding "
                    "the index again."
                )
            },
            status_code=429,
        )

    _last_rebuild[client] = now

    bot.ensure_index(force=True)

    return JSONResponse({
        "status": "rebuilt",
        **bot.stats(),
    })


app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("PORT", "8000")),
    )