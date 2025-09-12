import os, asyncio, time
from typing import Dict, Any, List, Tuple
from datetime import datetime
import pandas as pd

from backend.app.services import gmail_services, github_services
from backend.app.services.llm import draft_email_from_state, draft_message_from_state
from backend.app.pipelines.build_dataset_fast import build_state

_LAST_STATS: Dict[str, Any] = {
    "started_at": None, "finished_at": None,
    "gmail_found": 0, "discord_found": 0, "github_found": 0,
    "drafted": 0, "errors": [],
}
_LAST_EVENTS: Dict[str, List[Dict[str, Any]]] = {"gmail": [], "discord": [], "github": []}

def get_poll_stats() -> Dict[str, Any]: return dict(_LAST_STATS)
def get_last_events() -> Dict[str, List[Dict[str, Any]]]:
    return {k: list(v) for k, v in _LAST_EVENTS.items()}

async def fetch_new_gmail() -> List[Dict]:
    try:
        emails = gmail_services.fetch_recent_emails(limit=5)  # q=newer_than:7d
        events: List[Dict] = []
        for e in emails:
            try:
                ts = datetime.fromtimestamp(int(e.get("internalDate") or 0)/1000) if e.get("internalDate") else datetime.utcnow()
            except Exception:
                ts = datetime.utcnow()
            events.append({
                "id": e["id"], "thread_id": e.get("threadId") or e["id"],
                "actor": e.get("from"), "subject": e.get("subject"),
                "snippet": e.get("snippet"), "text": e.get("snippet") or "",
                "timestamp": ts, "source": "gmail",
            })
        return events
    except Exception as ex:
        print("[poll:gmail] error", ex)
        return []

async def fetch_new_discord() -> List[Dict]:
    import aiohttp
    token = os.getenv("DISCORD_BOT_TOKEN"); channel_ids_raw = os.getenv("DISCORD_CHANNEL_IDS","")
    if not token or not channel_ids_raw: return []
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    channel_ids = [x.strip() for x in channel_ids_raw.split(",") if x.strip()]
    out: List[Dict] = []
    async with aiohttp.ClientSession(headers=headers) as session:
        for cid in channel_ids:
            url = f"https://discord.com/api/v10/channels/{cid}/messages?limit=20"
            try:
                async with session.get(url) as r:
                    if r.status != 200:
                        print("[poll:discord]", cid, r.status, await r.text()); continue
                    for m in await r.json():
                        out.append({
                            "id": m.get("id"),
                            "thread_id": m.get("channel_id", cid),
                            "actor": (m.get("author") or {}).get("username","unknown"),
                            "text": m.get("content") or "",
                            "timestamp": m.get("timestamp"),
                            "source": "discord",
                        })
            except Exception as ex:
                print("[poll:discord] error", cid, ex)
    return out

async def fetch_new_github() -> List[Dict]:
    try: return github_services.fetch_recent_commits(limit_per_repo=30)
    except Exception as ex:
        print("[poll:github] error", ex); return []

async def _draft_for_events(source: str, events: List[Dict]) -> Tuple[int, List[str]]:
    errs, drafted = [], 0
    if not events: return 0, errs
    by_thread: Dict[str, List[Dict]] = {}
    for e in events:
        tid = e.get("thread_id") or f"{source}-{e.get('id','oneoff')}"
        by_thread.setdefault(tid, []).append(e)
    for tid, rows in by_thread.items():
        try:
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
            if source == "gmail":
                _ = draft_email_from_state(state=state, recipient=None, max_words=140)
            else:
                _ = draft_message_from_state(state=state, platform=source, max_words=140)
            drafted += 1
        except Exception as ex:
            errs.append(f"{source}:{tid}:{ex}")
    return drafted, errs

async def poll() -> Dict[str, Any]:
    _LAST_STATS.update(started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                       gmail_found=0, discord_found=0, github_found=0,
                       drafted=0, errors=[])
    gmail_events  = await fetch_new_gmail()
    discord_events= await fetch_new_discord()
    github_events = await fetch_new_github()
    _LAST_EVENTS["gmail"] = gmail_events
    _LAST_EVENTS["discord"] = discord_events
    _LAST_EVENTS["github"] = github_events
    _LAST_STATS["gmail_found"]   = len(gmail_events)
    _LAST_STATS["discord_found"] = len(discord_events)
    _LAST_STATS["github_found"]  = len(github_events)
    d1,e1 = await _draft_for_events("gmail", gmail_events)
    d2,e2 = await _draft_for_events("discord", discord_events)
    d3,e3 = await _draft_for_events("github", github_events)
    _LAST_STATS["drafted"] = d1 + d2 + d3
    _LAST_STATS["errors"] = [*e1, *e2, *e3]
    _LAST_STATS["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return dict(_LAST_STATS)

from apscheduler.schedulers.background import BackgroundScheduler
def start_scheduler():
    every = int(os.getenv("POLL_EVERY_SECONDS", "120"))
    sch = BackgroundScheduler()
    def _job():
        try: asyncio.run(poll())
        except Exception as e: _LAST_STATS["errors"].append(f"job:{e}")
    sch.add_job(_job, "interval", seconds=every)
    sch.start()
    print(f"📅 Scheduler started, polling every {every}s.")
