"""AVARIX FastAPI server with SQLite-backed college-domain authentication."""
from pathlib import Path
import hashlib, hmac, os, secrets, sqlite3, sys, time
from collections import defaultdict, deque
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
from app.chatbot import ChatBot

STATIC_DIR = Path(__file__).resolve().parent / "static"
DB_PATH = Path(os.getenv("AVARIX_USER_DB", str(PROJECT_ROOT / "avarix_users.db")))
SECRET = os.getenv("AVARIX_SESSION_SECRET") or ("local-dev-" + str(PROJECT_ROOT.resolve()))
app = FastAPI(title="AVARIX", description="Aerospace Intelligence & Knowledge Platform")
app.add_middleware(SessionMiddleware, secret_key=SECRET, session_cookie="avarix_session", same_site="lax", https_only=os.getenv("AVARIX_HTTPS_ONLY", "false").lower() in {"1", "true", "yes"}, max_age=604800)
chatbot = ChatBot()
RATE_LIMIT = max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")))
REBUILD_COOLDOWN = max(1, int(os.getenv("REBUILD_COOLDOWN_SECONDS", "60")))
requests_by_client, last_rebuild = defaultdict(deque), defaultdict(float)

class ChatRequest(BaseModel):
    question: str
    session_id: str = "default"
    rebuild_index: bool = False
class AuthRequest(BaseModel):
    email: str
    password: str
class SignupRequest(AuthRequest):
    name: str
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

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
def valid_email(email):
    local, sep, domain = (email or "").strip().lower().partition("@")
    return bool(sep and local and not any(c.isspace() for c in local) and "@" not in local and domain == "kcgcollege.com")
def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"
def verify_password(password, stored):
    try:
        scheme, salt_hex, digest_hex = stored.split("$", 2)
        if scheme != "scrypt": return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (ValueError, TypeError): return False
def current_user(request):
    uid = request.session.get("user_id")
    if not isinstance(uid, int): return None
    with db() as conn: return conn.execute("SELECT id,name,email FROM users WHERE id=?", (uid,)).fetchone()
def auth_error(): return JSONResponse({"detail":"Authentication required."}, status_code=401)
def client_id(request):
    return (request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")).strip()
def allowed(client):
    now=time.monotonic(); q=requests_by_client[client]
    while q and now-q[0]>60: q.popleft()
    if len(q)>=RATE_LIMIT: return False
    q.append(now); return True

@app.on_event("startup")
def startup():
    init_db(); chatbot.ensure_index()

@app.get("/")
def home(request: Request):
    return RedirectResponse("/app", 303) if current_user(request) else FileResponse(STATIC_DIR/"auth.html")
@app.get("/login")
def login_page(request: Request): return home(request)
@app.get("/signup")
def signup_page(request: Request): return home(request)
@app.get("/app")
def app_page(request: Request):
    return FileResponse(STATIC_DIR/"index.html") if current_user(request) else RedirectResponse("/", 303)


@app.get("/service-worker.js")
def service_worker():
    return FileResponse(
        STATIC_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

@app.post("/api/auth/signup")
def signup(req: SignupRequest, request: Request):
    email=(req.email or "").strip().lower(); name=(req.name or "").strip(); password=req.password or ""
    if not valid_email(email): return JSONResponse({"detail":"Use a valid @kcgcollege.com email address."},400)
    if not name or len(name)>120: return JSONResponse({"detail":"Enter a name of 1–120 characters."},400)
    if len(password)<8: return JSONResponse({"detail":"Password must contain at least 8 characters."},400)
    if len(password)>1024: return JSONResponse({"detail":"Password is too long."},400)
    try:
        with db() as conn:
            cur=conn.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",(name,email,hash_password(password)))
            uid=cur.lastrowid
    except sqlite3.IntegrityError:
        return JSONResponse({"detail":"An account with this email already exists. Please sign in."},409)
    request.session.clear(); request.session["user_id"]=int(uid)
    return {"status":"ok","name":name,"email":email}

@app.post("/api/auth/login")
def signin(req: AuthRequest, request: Request):
    email=(req.email or "").strip().lower()
    if not valid_email(email): return JSONResponse({"detail":"Use a valid @kcgcollege.com email address."},400)
    with db() as conn: user=conn.execute("SELECT id,name,email,password_hash FROM users WHERE email=? COLLATE NOCASE",(email,)).fetchone()
    if user is None or not verify_password(req.password or "",user["password_hash"]):
        return JSONResponse({"detail":"Email or password is incorrect."},401)
    request.session.clear(); request.session["user_id"]=int(user["id"])
    return {"status":"ok","name":user["name"],"email":user["email"]}
@app.post("/api/auth/logout")
def logout(request: Request): request.session.clear(); return {"status":"ok"}
@app.get("/api/auth/me")
def me(request: Request):
    user=current_user(request)
    if user is None: return JSONResponse({"authenticated":False},401)
    return {"authenticated":True,"name":user["name"],"email":user["email"]}
@app.get("/api/health")
def health(): return {"status":"ok",**chatbot.stats()}
@app.post("/api/chat",response_model=ChatResponse)
def chat(req: ChatRequest,request: Request):
    user=current_user(request)
    if user is None: return auth_error()
    client=client_id(request)
    if not allowed(client): return JSONResponse({"detail":"Too many requests. Please try again shortly."},429)
    sid=(req.session_id or "").strip()[:128] or "default"
    result=chatbot.answer(req.question,rebuild_index=req.rebuild_index,session_id=f"user:{user['id']}:{sid}")
    keys=("answer","case","source","db_results","web_results","aerocalc","mode","structured","visuals")
    data={k:result.get(k, [] if k in {"db_results","web_results","visuals"} else None) for k in keys}
    data["answer"]=result.get("answer","")
    return ChatResponse(**data)
@app.post("/api/rebuild")
def rebuild(request: Request):
    if current_user(request) is None: return auth_error()
    client=client_id(request); now=time.monotonic()
    if now-last_rebuild[client]<REBUILD_COOLDOWN: return JSONResponse({"error":"Please wait before rebuilding the index again."},429)
    last_rebuild[client]=now; chatbot.ensure_index(force=True)
    return {"status":"rebuilt",**chatbot.stats()}
app.mount("/static",StaticFiles(directory=str(STATIC_DIR)),name="static")
if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=int(os.getenv("PORT","8000")))
