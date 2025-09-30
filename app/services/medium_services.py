import os
import secrets
import urllib.parse
import requests
import feedparser
from typing import List, Dict

CLIENT_ID = os.getenv("MEDIUM_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("MEDIUM_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("MEDIUM_REDIRECT_URI", "")

AUTH_BASE = "https://medium.com/m/oauth/authorize"
TOKEN_URL = "https://api.medium.com/v1/tokens"

def generate_auth_url(state: str | None = None, scopes: List[str] | None = None) -> str:
    if not state:
        state = secrets.token_urlsafe(16)
    if not scopes:
        scopes = ["basicProfile", "listPublications", "publishPost"]
    params = {
        "client_id": CLIENT_ID,
        "scope": " ".join(scopes),
        "state": state,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI
    }
    return AUTH_BASE + "?" + urllib.parse.urlencode(params)

def exchange_code_for_token(code: str) -> dict:
    if not (CLIENT_ID and CLIENT_SECRET and REDIRECT_URI):
        raise RuntimeError("MEDIUM client env missing (MEDIUM_CLIENT_ID / MEDIUM_CLIENT_SECRET / MEDIUM_REDIRECT_URI)")
    payload = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    r = requests.post(TOKEN_URL, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_articles_by_username(username: str, limit: int = 20) -> List[Dict]:
    if not username:
        return []
    feed_url = f"https://medium.com/feed/@{username}"
    d = feedparser.parse(feed_url)
    out = []
    for e in d.entries[:limit]:
        content = ""
        if e.get("content"):
            # feedparser content may be list of dicts
            try:
                content = (e.get("content")[0].get("value") if isinstance(e.get("content"), list) else e.get("content"))
            except Exception:
                content = ""
        if not content:
            content = getattr(e, "summary", "") or ""
        out.append({
            "id": e.get("id") or e.get("link"),
            "title": e.get("title"),
            "link": e.get("link"),
            "published": e.get("published"),
            "summary": getattr(e, "summary", "") or "",
            "content": content
        })
    return out

def parse_username_from_token_info(token_info: dict) -> str:
    # Medium token response includes `data` with `username` under some cases
    data = token_info.get("data") or token_info
    username = data.get("username") or data.get("data", {}).get("username") or ""
    return username
