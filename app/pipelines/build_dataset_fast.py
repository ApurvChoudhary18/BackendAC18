from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_EVENTS = ROOT / "data" / "raw" / "events.jsonl"
PROC = ROOT / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)
OUT = PROC / "dataset.parquet"

YOU_TOKENS = {"you"}

def read_events():
    rows = []
    with open(RAW_EVENTS, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            rows.append({
                "id": o["id"],
                "source": o["source"],
                "actor": o.get("actor", "other"),
                "ts": pd.to_datetime(o["timestamp"], utc=True),
                "thread_id": o["thread_id"],
                "text": (o.get("text") or "").strip(),
            })
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)

def label_action(text: str) -> str | None:
    t = text.lower()
    urgent_keys = ["asap","eod","deadline","eta","urgent","priority","immediately","today","blocker"]
    if any(k in t for k in urgent_keys):
        return "reply_urgent"
    if "?" in t or any(k in t for k in ["can you","could you","please review","ptal","any update","status?"]):
        return "reply"
    return None

def finalize_label(thread_df: pd.DataFrame) -> str | None:
    # 1) prefer last non-you urgent/reply cues
    for i in reversed(range(len(thread_df))):
        r = thread_df.iloc[i]
        if r["actor"] not in YOU_TOKENS:
            la = label_action(r["text"])
            if la:
                return la
            break
    # 2) follow_up if last is not you & older than 24h
    last = thread_df.iloc[-1]
    if last["actor"] not in YOU_TOKENS:
        now_utc = pd.Timestamp.now(tz="UTC")   # FIXED
        age_s = (now_utc - last["ts"]).total_seconds()
        if age_s > 86400:
            return "follow_up"
    # 3) summarize if long thread or “closes/fixes/resolved”
    if len(thread_df) >= 10:
        return "summarize"
    for x in thread_df["text"].str.lower().tolist():
        if any(k in x for k in ["closes #", "fixes #", "resolved #"]):
            return "summarize"
    return None

def build_state(thread_df: pd.DataFrame, N: int = 5) -> str:
    ctx = thread_df.tail(N)
    srcs = ", ".join(sorted(ctx["source"].unique()))
    lines = [f"[Thread: {ctx.iloc[-1]['thread_id']} | Sources: {srcs}]"]
    for _, r in ctx.iterrows():
        when = r["ts"].strftime("%Y-%m-%d %H:%M")
        who = "you" if r["actor"] in YOU_TOKENS else "other"
        lines.append(f"{when} {who}: {r['text']}")
    return "\n".join(lines)

def main():
    df = read_events()
    rows = []
    for tid, g in df.groupby("thread_id", sort=False):
        g = g.sort_values("ts").reset_index(drop=True)
        for end in range(3, len(g) + 1):
            sub = g.iloc[:end]
            action = finalize_label(sub)
            if not action:
                continue
            state = build_state(sub, N=5)
            rows.append({
                "id": f"{tid}-{end}",
                "state": state,
                "action": action,
                "thread_id": tid,
                "timestamp_utc": sub.iloc[-1]["ts"].isoformat(),
            })
    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("No labeled rows produced. Check your events.jsonl or rules.")
    out.to_parquet(OUT, index=False)
    print(f"Saved {len(out)} rows → {OUT}")

if __name__ == "__main__":
    main()
