from dotenv import load_dotenv
load_dotenv()
from typing import Optional, Dict, Any
import os, json, re, time
from openai import OpenAI
DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
_client: Optional[OpenAI] = None
def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key and os.getenv("LLM_OFFLINE") != "1":
            raise RuntimeError("OPENAI_API_KEY not set")
        if os.getenv("LLM_OFFLINE") == "1":
            return None
        _client = OpenAI(api_key=api_key)
    return _client
def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```") and "json" in text.splitlines()[0].lower():
        text = "\n".join(text.splitlines()[1:-1])
    m = re.search(r"(\{(?:[^{}]|(?1))*\})", text, flags=re.DOTALL)
    if not m:
        m = re.search(r"(\{[\s\S]*\})", text, flags=re.DOTALL)
    if not m:
        return None
    candidate = m.group(1)
    try:
        return json.loads(candidate)
    except Exception:
        try:
            candidate_clean = re.sub(r",\s*}", "}", re.sub(r",\s*]", "]", candidate))
            return json.loads(candidate_clean)
        except Exception:
            return None
def _chat_json(system: str, user: str, model: Optional[str] = None, retries: int = 1, delay: float = 0.5) -> Dict[str, Any]:
    if os.getenv("LLM_OFFLINE") == "1":
        return {"subject": "Draft", "body": "Hi,\n\nOn it.\n\n—ShadowShift"}
    client = get_client()
    mdl = model or DEFAULT_LLM_MODEL
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = client.chat.completions.create(
                model=mdl,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            choices = getattr(resp, "choices", None) or resp.get("choices", [])
            if not choices:
                content = ""
            else:
                content = ""
                first = choices[0]
                msg = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
                if isinstance(msg, dict):
                    content = msg.get("content", "") or ""
                else:
                    content = getattr(msg, "content", "") or ""
            content = (content or "").strip()
            parsed = _extract_json_from_text(content)
            if parsed is not None:
                return parsed
            return {"subject": "Draft", "body": content or "Hi,\n\nThanks,\n"}
        except Exception as e:
            if attempt > retries:
                raise
            time.sleep(delay)
def draft_email_from_state(
    state: str,
    recipient: Optional[str] = None,
    style: str = "concise",
    tone: str = "professional",
    language: str = "en",
    max_words: int = 180,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    if os.getenv("LLM_OFFLINE") == "1":
        return {"subject": "Draft reply", "body": "Hi,\n\nOn it.\n\n—ShadowShift", "model": "offline"}
    user = f"""Language: {language}
Style: {style} | Tone: {tone} | Max words: {max_words}
Recipient: {recipient or "unknown"}

STATE:
{state}

Return JSON:
{{"subject": "...", "body": "..."}}"""
    data = _chat_json(
        "You are ShadowShift's email drafting assistant. Input is a serialized conversation state. Return ONLY a strict JSON object with keys: subject, body. No extra prose.",
        user,
        model,
        retries=2,
        delay=0.5,
    )
    data["model"] = model or DEFAULT_LLM_MODEL
    return data
def draft_message_from_state(
    state: str,
    platform: str,
    tone: str = "professional",
    language: str = "en",
    max_words: int = 120,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    if os.getenv("LLM_OFFLINE") == "1":
        return {"subject": "", "body": "Acknowledged. I'll follow up soon.", "model": "offline"}
    user = f"""Platform: {platform} | Tone: {tone} | Language: {language} | Max words: {max_words}

STATE:
{state}

Return JSON:
{{"body": "..."}}"""
    data = _chat_json(
        "You are ShadowShift's messaging assistant (Discord/GitHub). Return ONLY a strict JSON object with key: body. No extra prose.",
        user,
        model,
        retries=2,
        delay=0.5,
    )
    return {"subject": "", "body": (data.get("body") or data.get("text") or "").strip(), "model": model or DEFAULT_LLM_MODEL}
