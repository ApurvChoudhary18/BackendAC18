from pathlib import Path
from typing import Optional, List, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import Body
from backend.app.services.scheduler import get_last_events


from fastapi import APIRouter

# --- Load .envs ---
ROOT = Path(__file__).resolve().parents[3]        # .../ShadowShift
BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../ShadowShift/backend
load_dotenv(ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

# Project imports
from backend.app.models.ai_stub import AIStub
from backend.app.pipelines.build_dataset_fast import build_state
from backend.app.services.llm import draft_email_from_state, draft_message_from_state
from backend.app.services.scheduler import start_scheduler

# ---------- Paths ----------
DATASET = BACKEND_ROOT / "data" / "processed" / "dataset.parquet"
STORAGE = BACKEND_ROOT / "storage"
MODEL_PATH = STORAGE / "ai_stub.joblib"

# ---------- App ----------
app = FastAPI(title="ShadowShift API")

# CORS (dev open; prod: restrict to FE origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL: Optional[AIStub] = None
READY = False

# ---------- Schemas ----------
class RecommendIn(BaseModel):
    state: str
    threshold: float = 0.5

class RecommendOut(BaseModel):
    action: str
    confidence: float

class BatchIn(BaseModel):
    states: List[str]
    threshold: float = 0.5

class ActIn(BaseModel):
    source: Literal["gmail", "discord", "github"]
    state: Optional[str] = None
    events: Optional[List[dict]] = None
    tone: str = "professional"
    style: str = "concise"
    language: str = "en"
    max_words: int = 180
    model: Optional[str] = None
    recipient: Optional[str] = None  # for email only
    threshold: float = 0.45

class ActOut(BaseModel):
    action: str
    confidence: float
    subject: str
    body: str
    model: str
    used_state: str

# ---------- Utils ----------
def _exists_and_newer(path_a: Path, path_b: Path) -> bool:
    if not path_a.exists():
        return False
    if not path_b.exists():
        return True
    return path_a.stat().st_mtime >= path_b.stat().st_mtime

# ---------- Lifecycle ----------
@app.on_event("startup")
def startup():
    """Load or (re)fit the baseline model."""
    global READY, MODEL
    READY = False
    STORAGE.mkdir(parents=True, exist_ok=True)

    if not DATASET.exists():
        print(f"[startup] Dataset missing at {DATASET}")
        return

    try:
        if _exists_and_newer(MODEL_PATH, DATASET):
            MODEL = AIStub.load(MODEL_PATH)
            print(f"[startup] Loaded model from {MODEL_PATH}")
        else:
            df = pd.read_parquet(DATASET)
            MODEL = AIStub()
            MODEL.fit(df)
            MODEL.save(MODEL_PATH)
            print(f"[startup] Fitted & saved model → {MODEL_PATH}")
        READY = True
    except Exception as e:
        print(f"[startup] init error: {e}")
        READY = False

@app.on_event("startup")
def start_bg_tasks():
    try:
        start_scheduler()
    except Exception as e:
        print(f"[scheduler] Failed to start: {e}")

# ---------- Routes ----------
@app.get("/health")
def health():
    return {
        "ready": READY,
        "dataset_exists": DATASET.exists(),
        "model_path": str(MODEL_PATH),
        "model_saved": MODEL_PATH.exists(),
    }

@app.get("/config")
def config():
    return {
        "ngram_range": getattr(MODEL, "_ngram_range", None),
        "n_neighbors": getattr(MODEL, "_n_neighbors", None),
        "ready": READY,
    }

@app.post("/recommend", response_model=RecommendOut)
def recommend(inp: RecommendIn):
    if not READY or MODEL is None:
        raise HTTPException(status_code=503, detail="Model not ready")
    if not inp.state or not inp.state.strip():
        raise HTTPException(status_code=422, detail="state cannot be empty")
    if not (0.0 <= float(inp.threshold) <= 1.0):
        raise HTTPException(status_code=422, detail="threshold must be in [0,1]")

    pred = MODEL.predict_with_threshold(inp.state, threshold=float(inp.threshold))
    return RecommendOut(**pred)

@app.post("/batch", response_model=List[RecommendOut])
def batch(inp: BatchIn):
    if not READY or MODEL is None:
        raise HTTPException(status_code=503, detail="Model not ready")
    if not inp.states:
        raise HTTPException(status_code=422, detail="states cannot be empty")
    if not (0.0 <= float(inp.threshold) <= 1.0):
        raise HTTPException(status_code=422, detail="threshold must be in [0,1]")

    out = [MODEL.predict_with_threshold(s, threshold=float(inp.threshold)) for s in inp.states]
    return [RecommendOut(**o) for o in out]

@app.post("/act", response_model=ActOut)
def act(inp: ActIn):
    if inp.state:
        state_str = inp.state
    elif inp.events:
        df = pd.DataFrame(inp.events)
        if "ts" not in df.columns and "timestamp" in df.columns:
            df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
        if "actor" not in df.columns:
            df["actor"] = df.get("author") or "other"
        df = df.sort_values("ts").reset_index(drop=True)
        state_str = build_state(df, N=5)
    else:
        raise HTTPException(status_code=422, detail="Provide either 'state' or 'events'")

    action_pred = {"action": "reply", "confidence": 0.5}
    try:
        if READY and MODEL is not None:
            action_pred = MODEL.predict_with_threshold(state_str, threshold=float(inp.threshold))
    except Exception:
        pass

    try:
        if inp.source == "gmail":
            draft = draft_email_from_state(
                state=state_str,
                recipient=inp.recipient,
                style=inp.style,
                tone=inp.tone,
                language=inp.language,
                max_words=inp.max_words,
                model=inp.model,
            )
        elif inp.source in ("discord", "github"):
            draft = draft_message_from_state(
                state=state_str,
                platform=inp.source,
                tone=inp.tone,
                language=inp.language,
                max_words=min(inp.max_words, 300),
                model=inp.model,
            )
        else:
            raise RuntimeError("Unsupported source")
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"LLM draft failed: {e}")

    return ActOut(
        action=str(action_pred.get("action", "reply")),
        confidence=float(action_pred.get("confidence", 0.5)),
        subject=draft.get("subject", ""),
        body=draft.get("body", ""),
        model=draft.get("model", ""),
        used_state=state_str,
    )

@app.get("/debug/env2")
def debug_env2():
    import os
    keys = [
        "CLIENT_ID","CLIENT_SECRET","REDIRECT_URI","GMAIL_REFRESH_TOKEN",
        "DISCORD_BOT_TOKEN","DISCORD_CHANNEL_IDS",
        "GITHUB_TOKEN","GITHUB_REPOS","GITHUB_NEWER_THAN_MIN",
        "OPENAI_API_KEY","LLM_OFFLINE","LLM_MODEL",
    ]
    return {k: (os.getenv(k)[:6] + "..." if os.getenv(k) else "") for k in keys}

@app.post("/poll/now")
def poll_now():
    from backend.app.services.scheduler import poll
    import asyncio
    stats = asyncio.run(poll())
    return stats

@app.get("/poll/stats")
def poll_stats():
    from backend.app.services.scheduler import get_poll_stats
    return get_poll_stats()


@app.get("/inbox")
def inbox():
    """
    FE ko latest fetched items (gmail/discord/github) dene ke liye.
    """
    return get_last_events()

class DraftFromThreadIn(BaseModel):
    source: Literal["gmail", "discord", "github"]
    thread_id: str
    max_words: int = 180
    model: Optional[str] = None

class DraftFreeIn(BaseModel):
    source: Literal["gmail", "discord", "github"]
    messages: List[dict]  # each: {actor, text, ts?}
    max_words: int = 180
    model: Optional[str] = None

@app.post("/draft/from-thread")
def draft_from_thread(inp: DraftFromThreadIn):
    events_by_source = get_last_events()
    rows = [e for e in events_by_source.get(inp.source, []) if str(e.get("thread_id")) == str(inp.thread_id)]
    if not rows:
        raise HTTPException(status_code=404, detail="Thread not found in last poll")

    df = pd.DataFrame(rows)
    if "ts" not in df.columns and "timestamp" in df.columns:
        df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df["ts"] = df["ts"].fillna(pd.Timestamp.utcnow())
    if "actor" not in df.columns:
        df["actor"] = df.get("author") or "other"
    if "text" not in df.columns:
        df["text"] = df.get("snippet") or ""

    df = df.sort_values("ts").reset_index(drop=True)
    state = build_state(df, N=5)

    try:
        if inp.source == "gmail":
            draft = draft_email_from_state(state=state, recipient=None, max_words=inp.max_words, model=inp.model)
        else:
            draft = draft_message_from_state(state=state, platform=inp.source, max_words=inp.max_words, model=inp.model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM draft failed: {e}")

    return {
        "state": state,
        "subject": draft.get("subject", ""),
        "body": draft.get("body", ""),
        "model": draft.get("model", ""),
    }

@app.post("/draft/free")
def draft_free(inp: DraftFreeIn):
    if not inp.messages:
        raise HTTPException(status_code=422, detail="messages cannot be empty")

    df = pd.DataFrame(inp.messages)
    if "ts" not in df.columns and "timestamp" in df.columns:
        df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df["ts"] = df["ts"].fillna(pd.Timestamp.utcnow())
    if "actor" not in df.columns:
        df["actor"] = df.get("author") or "other"
    if "text" not in df.columns:
        df["text"] = df.get("snippet") or ""

    df = df.sort_values("ts").reset_index(drop=True)
    state = build_state(df, N=5)

    try:
        if inp.source == "gmail":
            draft = draft_email_from_state(state=state, recipient=None, max_words=inp.max_words, model=inp.model)
        else:
            draft = draft_message_from_state(state=state, platform=inp.source, max_words=inp.max_words, model=inp.model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM draft failed: {e}")

    return {
        "state": state,
        "subject": draft.get("subject", ""),
        "body": draft.get("body", ""),
        "model": draft.get("model", ""),
    }

# ---- SEND: Schemas ----
from pydantic import BaseModel

class SendGmailIn(BaseModel):
    to: str
    subject: str
    body: str
    thread_id: str | None = None
    in_reply_to: str | None = None  # optional message-id if available

class SendDiscordIn(BaseModel):
    channel_id: str
    content: str

# ---- SEND: Gmail ----
@app.post("/send/gmail")
def send_gmail_endpoint(inp: SendGmailIn):
    from backend.app.services import gmail_services
    try:
        res = gmail_services.send_gmail(
            to=inp.to,
            subject=inp.subject,
            body=inp.body,
            thread_id=inp.thread_id,
            in_reply_to=inp.in_reply_to
        )
        return {"ok": True, "message_id": res.get("id"), "thread_id": res.get("threadId")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail send failed: {e}")

# ---- SEND: Discord ----
@app.post("/send/discord")
def send_discord_endpoint(inp: SendDiscordIn):
    import os, requests, json
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="DISCORD_BOT_TOKEN missing")

    url = f"https://discord.com/api/v10/channels/{inp.channel_id}/messages"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    data = {"content": inp.content}

    r = requests.post(url, headers=headers, data=json.dumps(data), timeout=20)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Discord send failed: {r.status_code} {r.text}")

    return {"ok": True, "message_id": r.json().get("id")}

