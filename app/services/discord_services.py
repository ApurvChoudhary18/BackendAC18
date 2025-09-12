import os
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

DISCORD_API_BASE = "https://discord.com/api/v10"


def _get_token() -> str:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN in env")
    return token


def _get_channels() -> List[str]:
    chans = os.getenv("DISCORD_CHANNEL_IDS") or ""
    return [c.strip() for c in chans.split(",") if c.strip()]


def _auth_headers() -> Dict[str, str]:
    return {"Authorization": f"Bot {_get_token()}"}


def fetch_recent_messages(limit: int = 20) -> List[Dict]:
    out: List[Dict] = []
    newer_than_min = int(os.getenv("DISCORD_NEWER_THAN_MIN") or "0")
    cutoff = None
    if newer_than_min > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=newer_than_min)

    for channel_id in _get_channels():
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages?limit={limit}"
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=10)
            resp.raise_for_status()
            msgs = resp.json()
            for m in msgs:
                ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
                if cutoff and ts < cutoff:
                    continue
                out.append(
                    {
                        "id": m["id"],
                        "thread_id": channel_id,
                        "actor": m["author"]["username"],
                        "text": m.get("content", ""),
                        "timestamp": ts.isoformat(),
                        "source": "discord",
                    }
                )
        except Exception as e:
            print(f"[discord] fetch error for channel {channel_id}: {e}")
    return out


def send_message(channel_id: str, content: str) -> Dict:
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json={"content": content},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[discord] send error: {e}")
        raise
