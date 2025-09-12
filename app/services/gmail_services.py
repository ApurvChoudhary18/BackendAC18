import os
from typing import List, Dict, Optional

import base64
from email.mime.text import MIMEText
from email.utils import formatdate

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def _get_service():
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    if not (refresh_token and client_id and client_secret):
        raise RuntimeError("Gmail env missing (CLIENT_ID / CLIENT_SECRET / GMAIL_REFRESH_TOKEN).")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def _header(headers: List[Dict], name: str) -> Optional[str]:
    for h in headers or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None

def _extract_bodies(payload: Dict) -> Dict[str, str]:
    def decode(data: Optional[str]) -> str:
        if not data:
            return ""
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    body_text, body_html = "", ""
    def walk(part: Dict):
        nonlocal body_text, body_html
        if not part:
            return
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data and mime:
            decoded = decode(data)
            if mime.startswith("text/plain"):
                body_text += decoded
            elif mime.startswith("text/html"):
                body_html += decoded
        for p in (part.get("parts") or []):
            walk(p)
    walk(payload)
    if not body_text and body_html:
        import re
        body_text = re.sub(r"<[^>]*>", " ", body_html)
        body_text = re.sub(r"\s+", " ", body_text).strip()
    return {"bodyText": body_text, "bodyHtml": body_html}

def _is_promotional(msg_meta: Dict, bodies: Dict) -> bool:
    frm = (msg_meta.get("from") or "").lower()
    subj = (msg_meta.get("subject") or "").lower()
    txt = (bodies.get("bodyText") or "").lower() + " " + (bodies.get("bodyHtml") or "").lower()
    if "unsubscribe" in subj or "unsubscribe" in txt:
        return True
    if "no-reply" in frm or "noreply" in frm or "newsletter" in frm or "mailer-daemon" in frm:
        return True
    return False

def fetch_recent_emails(limit: int = 10, query: Optional[str] = None, exclude_promotions: bool = True) -> List[Dict]:
    service = _get_service()
    q = query if query is not None else "newer_than:7d"
    if exclude_promotions:
        q = f"{q} -category:promotions"
    res = service.users().messages().list(userId="me", q=q, maxResults=limit).execute()
    msgs_meta = res.get("messages", []) or []
    out: List[Dict] = []
    for m in msgs_meta:
        msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        frm = _header(headers, "From") or ""
        subject = _header(headers, "Subject") or ""
        bodies = _extract_bodies(payload)
        item = {
            "id": msg.get("id"),
            "threadId": msg.get("threadId"),
            "from": frm,
            "subject": subject,
            "snippet": msg.get("snippet", ""),
            "internalDate": msg.get("internalDate"),
            "bodyText": bodies["bodyText"],
            "bodyHtml": bodies["bodyHtml"],
        }
        if exclude_promotions and _is_promotional({"from": frm, "subject": subject}, bodies):
            continue
        out.append(item)
    return out

def send_gmail(
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    html: bool = False,
) -> Dict:
    service = _get_service()
    try:
        mime = MIMEText(body, _subtype=("html" if html else "plain"), _charset="utf-8")
        mime["To"] = to
        mime["Subject"] = subject
        mime["Date"] = formatdate(localtime=True)
        if in_reply_to:
            mime["In-Reply-To"] = in_reply_to
            mime["References"] = in_reply_to
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
        body_obj: Dict[str, object] = {"raw": raw}
        if thread_id:
            body_obj["threadId"] = thread_id
        sent = service.users().messages().send(userId="me", body=body_obj).execute()
        return sent
    except HttpError as error:
        print(f"[gmail] send error: {error}")
        raise
    except Exception:
        import traceback; traceback.print_exc()
        raise
