import os, requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

def fetch_recent_commits(limit_per_repo: int = 20):
    TOKEN = os.getenv("GITHUB_TOKEN")
    REPOS = os.getenv("GITHUB_REPOS", "")
    NEWER_THAN_MIN = int(os.getenv("GITHUB_NEWER_THAN_MIN", "1440"))
    if not TOKEN or not REPOS:
        print("[github] missing token or repos")
        return []
    headers = {"Authorization": f"token {TOKEN}"}
    repos = [r.strip() for r in REPOS.split(",") if r.strip()]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=NEWER_THAN_MIN)
    events = []
    for repo in repos:
        url = f"https://api.github.com/repos/{repo}/commits"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"[github] {repo} error {resp.status_code}: {resp.text}")
                continue
            for c in resp.json()[:limit_per_repo]:
                commit = c.get("commit", {})
                author = commit.get("author", {})
                date_str = author.get("date")
                try:
                    ts = datetime.fromisoformat(date_str.replace("Z","+00:00")) if date_str else datetime.now(timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)
                if ts < cutoff: continue
                events.append({
                    "id": c.get("sha"),
                    "thread_id": repo,
                    "actor": author.get("name") or "unknown",
                    "text": commit.get("message",""),
                    "timestamp": ts,
                    "source": "github",
                })
        except Exception as ex:
            print("[github] error", repo, ex)
    return events
