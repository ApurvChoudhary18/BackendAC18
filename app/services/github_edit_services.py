import os
import base64
import json
import typing
import logging
from typing import Optional, Dict, Any, List

import requests

from backend.app.services import llm

LOG = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


def _gh_headers():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _repo_owner_and_name(repo_full: str) -> (str, str):
    if "/" not in repo_full:
        raise ValueError("GITHUB_REPOS must be of the form owner/repo")
    owner, name = repo_full.split("/", 1)
    return owner, name


def get_default_branch(repo_full: Optional[str] = None) -> str:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{name}", headers=_gh_headers())
    r.raise_for_status()
    return r.json().get("default_branch", "main")


def list_commits(repo_full: Optional[str] = None, per_page: int = 20) -> List[Dict[str, Any]]:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{name}/commits?per_page={per_page}", headers=_gh_headers())
    r.raise_for_status()
    return r.json()


def get_file_contents(path: str, repo_full: Optional[str] = None, ref: Optional[str] = None) -> Dict[str, Any]:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)
    url = f"{GITHUB_API}/repos/{owner}/{name}/contents/{path}"
    params = {}
    if ref:
        params["ref"] = ref
    r = requests.get(url, headers=_gh_headers(), params=params)
    r.raise_for_status()
    data = r.json()
    content = ""
    if data.get("encoding") == "base64" and data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    else:
        content = data.get("content", "")
    return {"path": path, "sha": data.get("sha"), "content": content, "raw": data}


def create_branch(branch_name: str, from_branch: Optional[str] = None, repo_full: Optional[str] = None) -> Dict[str, Any]:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)
    base = from_branch or get_default_branch(repo_full)
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{name}/git/ref/heads/{base}", headers=_gh_headers())
    r.raise_for_status()
    base_sha = r.json()["object"]["sha"]
    payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
    r2 = requests.post(f"{GITHUB_API}/repos/{owner}/{name}/git/refs", headers=_gh_headers(), json=payload)
    r2.raise_for_status()
    return r2.json()


def update_file(path: str, content: str, message: str, branch: str, sha: Optional[str] = None, repo_full: Optional[str] = None) -> Dict[str, Any]:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)
    url = f"{GITHUB_API}/repos/{owner}/{name}/contents/{path}"
    b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload: Dict[str, Any] = {"message": message, "content": b64, "branch": branch}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=_gh_headers(), json=payload)
    r.raise_for_status()
    return r.json()


def create_pull_request(title: str, head_branch: str, base_branch: Optional[str] = None, body: str = "", repo_full: Optional[str] = None) -> Dict[str, Any]:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)
    base = base_branch or get_default_branch(repo_full)
    payload = {"title": title, "head": head_branch, "base": base, "body": body}
    r = requests.post(f"{GITHUB_API}/repos/{owner}/{name}/pulls", headers=_gh_headers(), json=payload)
    r.raise_for_status()
    return r.json()


def suggest_code_changes_via_llm(file_path: str, file_content: str, instructions: str, max_words: int = 400) -> Dict[str, Any]:
    state = f"FILE_PATH: {file_path}\n\nCURRENT_FILE_CONTENT:\n{file_content}\n\nINSTRUCTIONS:\n{instructions}"
    draft = llm.draft_message_from_state(state, platform="github", tone="helpful", max_words=max_words)
    suggestion = draft.get("body", "")
    return {"suggestion": suggestion, "model": draft.get("model", "")}


def apply_llm_suggestion_as_file_update(
    path: str,
    repo_full: Optional[str],
    instructions: str,
    new_branch: Optional[str] = None,
    pr_title: Optional[str] = None,
    base_branch: Optional[str] = None,
) -> Dict[str, Any]:
    repo_full = repo_full or os.getenv("GITHUB_REPOS")
    owner, name = _repo_owner_and_name(repo_full)

    file_info = get_file_contents(path, repo_full=repo_full)
    current = file_info["content"]
    sha = file_info.get("sha")

    branch = new_branch or f"shadowshift/auto-{os.urandom(3).hex()}"
    create_branch(branch, from_branch=base_branch, repo_full=repo_full)

    suggestion_obj = suggest_code_changes_via_llm(path, current, instructions)
    suggestion = suggestion_obj.get("suggestion", "").strip()

    if not suggestion:
        raise RuntimeError("LLM returned empty suggestion")

    # Heuristic: if suggestion looks like a full file, use it directly; else append suggestion as patch comment.
    if _looks_like_code_file(suggestion):
        updated_content = suggestion
    else:
        updated_content = _apply_plain_text_suggestion_to_file(current, suggestion)

    commit_msg = pr_title or f"chore: apply shadowshift suggestion to {path}"
    update_resp = update_file(path=path, content=updated_content, message=commit_msg, branch=branch, sha=sha, repo_full=repo_full)

    pr = create_pull_request(title=pr_title or commit_msg, head_branch=branch, base_branch=base_branch, body=f"Applied ShadowShift suggestion.\n\nLLM model: {suggestion_obj.get('model')}", repo_full=repo_full)
    return {"update": update_resp, "pull_request": pr, "suggestion": suggestion_obj}


def _looks_like_code_file(text: str) -> bool:
    lines = text.strip().splitlines()
    if not lines:
        return False
    # if contains common code tokens, assume full file
    indicators = ["def ", "class ", "{", "import ", "#!", "package ", "from ", "public ", "function "]
    score = sum(1 for i in indicators if i in text)
    return score >= 1


def _apply_plain_text_suggestion_to_file(original: str, suggestion: str) -> str:
    # Simple heuristic: if suggestion contains "replace between" markers, try to parse ranges.
    # Otherwise append suggestion as a trailing comment block.
    if "```" in suggestion and suggestion.strip().startswith("```"):
        # strip code fences
        s = suggestion.strip("`")
        # try to find the first code block
        i = s.find("\n")
        return s[i + 1 :] if i >= 0 else s
    # fallback: append suggestion at end with separator
    sep = "\n\n# --- ShadowShift suggested changes (append) ---\n"
    return original + sep + suggestion


# convenience wrapper used by API endpoints / CLI
def generate_pr_for_path(path: str, instructions: str, repo_full: Optional[str] = None, new_branch: Optional[str] = None, pr_title: Optional[str] = None):
    try:
        repo_full = repo_full or os.getenv("GITHUB_REPOS")
        res = apply_llm_suggestion_as_file_update(
            path=path,
            repo_full=repo_full,
            instructions=instructions,
            new_branch=new_branch,
            pr_title=pr_title,
        )
        return {"ok": True, "result": res}
    except Exception as e:
        LOG.exception("generate_pr_for_path failed")
        return {"ok": False, "error": str(e)}
