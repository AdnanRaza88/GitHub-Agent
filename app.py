from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="GitHub Agent",
    page_icon="https://github.githubassets.com/favicons/favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
.stApp {
background: linear-gradient(145deg, #0284c7 0%, #0ea5e9 35%, #38bdf8 70%, #7dd3fc 100%);
background-attachment: fixed; color: #0f172a;
}
section[data-testid="stSidebar"] {
background: rgba(255, 255, 255, 0.22) !important;
backdrop-filter: blur(18px) saturate(160%);
-webkit-backdrop-filter: blur(18px) saturate(160%);
border-right: 1px solid rgba(255, 255, 255, 0.45) !important;
box-shadow: 4px 0 24px rgba(3, 105, 161, 0.12);
}
section[data-testid="stSidebar"] * { color: #0f172a !important; font-weight: 600 !important; }
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stCaption"] {
color: #0c4a6e !important; font-weight: 500 !important; text-shadow: none !important;
}
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stTextArea textarea {
background: rgba(255, 255, 255, 0.92) !important; color: #0f172a !important;
border: 1px solid rgba(255, 255, 255, 0.7) !important; border-radius: 12px !important;
font-weight: 600 !important;
}
h1 {
color: #ffffff !important; font-weight: 800 !important; letter-spacing: -0.03em;
text-shadow: 0 2px 12px rgba(3, 105, 161, 0.35);
}
h2, h3 { color: #0f172a !important; font-weight: 700 !important; }
.stButton > button {
background: linear-gradient(135deg, #ffffff 0%, #e0f2fe 100%) !important;
color: #0c4a6e !important; border: 1px solid rgba(255, 255, 255, 0.8) !important;
border-radius: 12px !important; font-weight: 700 !important;
box-shadow: 0 4px 16px rgba(3, 105, 161, 0.18);
}
.stButton > button:hover {
background: linear-gradient(135deg, #f0f9ff 0%, #bae6fd 100%) !important;
}
.stDownloadButton > button {
background: rgba(255, 255, 255, 0.95) !important; color: #0369a1 !important;
border: 1.5px solid #7dd3fc !important; border-radius: 12px !important; font-weight: 700 !important;
}
[data-testid="stChatMessage"] {
background: rgba(255, 255, 255, 0.88) !important;
backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.65) !important;
border-radius: 16px !important; padding: 0.85rem 1.1rem; margin-bottom: 0.55rem;
box-shadow: 0 8px 28px rgba(3, 105, 161, 0.12);
}
[data-testid="stChatMessage"] * { color: #0f172a !important; font-weight: 600 !important; }
.stCaption, [data-testid="stCaption"] {
color: #ffffff !important; font-weight: 600 !important;
text-shadow: 0 1px 6px rgba(3, 105, 161, 0.3);
}
section[data-testid="stSidebar"] .stCaption { color: #0c4a6e !important; text-shadow: none !important; }
.stCodeBlock, pre {
background: rgba(15, 23, 42, 0.9) !important; color: #e0f2fe !important; border-radius: 12px !important;
}
div[data-baseweb="select"] > div {
background: rgba(255, 255, 255, 0.92) !important; color: #0f172a !important;
border-radius: 12px !important; font-weight: 600 !important;
}
.stRadio label, .stCheckbox label { color: #0f172a !important; font-weight: 700 !important; }
footer, #MainMenu { visibility: hidden; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PROVIDERS = {
    "OpenRouter": {
        "kind": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "defaults": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "openai/gpt-oss-20b:free",
            "openai/gpt-oss-120b:free",
            "qwen/qwen3-coder:free",
            "google/gemma-2-9b-it:free",
        ],
    },
    "Groq": {
        "kind": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "defaults": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
        ],
    },
    "Grok (xAI)": {
        "kind": "openai",
        "base_url": "https://api.x.ai/v1",
        "defaults": ["grok-4", "grok-3", "grok-2"],
    },
    "Gemini": {
        "kind": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "defaults": [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.5-flash",
        ],
    },
}

ROOT = Path(__file__).parent
SETTINGS = ROOT / "github_agent_settings.json"
NOTES = ROOT / "notes"
NOTES.mkdir(exist_ok=True)

SYSTEM = """You are GitHub Agent, a professional coding assistant for GitHub repositories.

When an action is required, reply with a short plan then one JSON block:

```json
{"action":"create_repo|update_visibility|delete_repo|create_file|update_file|read_file|list_repos|delete_file|zip_files|save_markdown|other","params":{},"explanation":"brief"}
```

Supported actions:
- create_repo: name, description?, private? (bool)
- update_visibility: owner?, repo, private (bool)
- delete_repo: owner?, repo
- create_file / update_file: owner?, repo, path, content, message, branch?
- read_file: owner?, repo, path, ref?
- list_repos
- delete_file: owner?, repo, path, message, branch?
- zip_files
- save_markdown: filename, content
- other

Rules:
- Always confirm before delete_repo or delete_file.
- Honor private/public choice exactly.
- Be concise. Produce complete clean code. No emojis.
- If the user spoke via voice, treat their transcript carefully; fix obvious speech recognition errors when intent is clear.
"""


def load_json(path: Path, default: Any = None) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {} if default is None else default


def save_json(path: Path, data: Any) -> bool:
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def compact(messages: List[Dict], budget: int = 5500) -> List[Dict]:
    total = sum(tokens(m.get("content", "")) for m in messages)
    if total < budget or len(messages) <= 6:
        return messages
    recent = messages[-6:]
    older = messages[:-6]
    summary = "Previous context:\n" + "\n".join(
        f"{m.get('role')}: {(m.get('content') or '')[:160]}" for m in older[-8:]
    )
    return [{"role": "system", "content": summary}] + recent


def fetch_models(provider: str, api_key: str) -> List[str]:
    cfg = PROVIDERS.get(provider, PROVIDERS["OpenRouter"])
    if not api_key:
        return cfg["defaults"]
    if cfg.get("kind") == "gemini":
        try:
            r = requests.get(
                f"{cfg['base_url']}/models",
                params={"key": api_key},
                timeout=20,
            )
            if r.status_code == 200:
                ids = []
                for m in r.json().get("models", []):
                    name = m.get("name", "")
                    if not name.startswith("models/"):
                        continue
                    mid = name.replace("models/", "")
                    methods = m.get("supportedGenerationMethods") or []
                    if "generateContent" in methods and "embed" not in mid.lower() and "tts" not in mid.lower():
                        ids.append(mid)
                if ids:
                    return sorted(ids)[:50]
        except Exception:
            pass
        return cfg["defaults"]
    try:
        r = requests.get(
            f"{cfg['base_url']}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if r.status_code == 200:
            ids = [m["id"] for m in r.json().get("data", []) if m.get("id")]
            if provider == "OpenRouter":
                free = sorted(x for x in ids if x.endswith(":free"))
                paid = sorted(x for x in ids if not x.endswith(":free"))
                return (free + paid)[:50]
            return sorted(ids)[:50]
    except Exception:
        pass
    return cfg["defaults"]


def call_gemini(api_key: str, model: str, messages: List[Dict], system: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    contents = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m.get("content") or ""}]})
    body: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": 4096},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    try:
        r = requests.post(
            url,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=body,
            timeout=90,
        )
        if r.status_code == 200:
            data = r.json()
            cands = data.get("candidates") or []
            if not cands:
                return "Empty response from Gemini."
            parts = (cands[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts) or "Empty text."
        return f"Error {r.status_code}: {r.text[:700]}"
    except Exception as e:
        return f"Request failed: {e}"


def call_llm(provider: str, api_key: str, model: str, messages: List[Dict], system: str) -> str:
    if not api_key:
        return "Enter a valid API key."
    if not model:
        return "Select a model (Fetch Models first)."
    cfg = PROVIDERS.get(provider, PROVIDERS["OpenRouter"])
    if cfg.get("kind") == "gemini":
        return call_gemini(api_key, model, messages, system)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "OpenRouter":
        headers["HTTP-Referer"] = "https://github.com/AdnanRaza88/GitHub-Agent"
        headers["X-Title"] = "GitHub Agent"
    body = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "temperature": 0.15,
        "max_tokens": 4096,
    }
    try:
        r = requests.post(f"{cfg['base_url']}/chat/completions", headers=headers, json=body, timeout=90)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        text = r.text[:700]
        if r.status_code == 401:
            return f"Invalid API key for {provider}."
        if r.status_code == 404:
            return (
                f"Model unavailable: `{model}`.\n"
                "Click Fetch Models and pick a current model."
            )
        return f"Error {r.status_code}: {text}"
    except Exception as e:
        return f"Request failed: {e}"


def gh_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh_user(token: str) -> Optional[Dict]:
    try:
        r = requests.get("https://api.github.com/user", headers=gh_headers(token), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def gh_create_repo(token: str, name: str, description: str = "", private: bool = True) -> Dict:
    r = requests.post(
        "https://api.github.com/user/repos",
        headers=gh_headers(token),
        json={"name": name, "description": description, "private": private, "auto_init": True},
        timeout=20,
    )
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def gh_set_visibility(token: str, owner: str, repo: str, private: bool) -> Dict:
    r = requests.patch(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=gh_headers(token),
        json={"private": private},
        timeout=15,
    )
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def gh_delete_repo(token: str, owner: str, repo: str) -> Dict:
    r = requests.delete(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=gh_headers(token),
        timeout=20,
    )
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def gh_put_file(token: str, owner: str, repo: str, path: str, content: str, message: str, branch: str = "main") -> Dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    sha = None
    try:
        r = requests.get(url, headers=gh_headers(token), params={"ref": branch}, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass
    body = {"message": message, "content": base64.b64encode(content.encode()).decode(), "branch": branch}
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=gh_headers(token), json=body, timeout=20)
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def gh_get_file(token: str, owner: str, repo: str, path: str, ref: str = "main") -> Optional[str]:
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=gh_headers(token),
            params={"ref": ref},
            timeout=15,
        )
        if r.status_code == 200 and r.json().get("encoding") == "base64":
            return base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def gh_list_repos(token: str) -> List[Dict]:
    try:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers(token),
            params={"per_page": 100, "sort": "updated"},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def gh_delete_file(token: str, owner: str, repo: str, path: str, message: str, branch: str = "main") -> Dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    r0 = requests.get(url, headers=gh_headers(token), params={"ref": branch}, timeout=10)
    if r0.status_code != 200:
        return {"status": r0.status_code, "data": r0.json() if r0.content else {}}
    sha = r0.json().get("sha")
    r = requests.delete(url, headers=gh_headers(token), json={"message": message, "sha": sha, "branch": branch}, timeout=15)
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def make_zip(files: Dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def save_markdown_note(filename: str, content: str) -> Path:
    safe = re.sub(r"[^\w.\-]+", "_", filename).strip("_") or "note"
    if not safe.endswith(".md"):
        safe += ".md"
    path = NOTES / safe
    path.write_text(content, encoding="utf-8")
    return path


def run_action(action: str, params: Dict, token: str, user: Optional[Dict]) -> str:
    owner_default = (user or {}).get("login", "")

    if action == "create_repo":
        res = gh_create_repo(
            token, params.get("name", "new-repo"), params.get("description", ""),
            bool(params.get("private", True)),
        )
        if res["status"] in (200, 201):
            d = res["data"]
            vis = "private" if d.get("private") else "public"
            return f"Created ({vis}): {d.get('html_url')}"
        return f"Failed: {res.get('data')}"

    if action == "update_visibility":
        owner = params.get("owner") or owner_default
        res = gh_set_visibility(token, owner, params.get("repo", ""), bool(params.get("private", True)))
        if res["status"] == 200:
            vis = "private" if res["data"].get("private") else "public"
            return f"Visibility set to {vis}: {res['data'].get('html_url')}"
        return f"Failed: {res.get('data')}"

    if action == "delete_repo":
        owner = params.get("owner") or owner_default
        repo = params.get("repo", "")
        if not repo:
            return "Repo name required for delete_repo."
        res = gh_delete_repo(token, owner, repo)
        if res["status"] in (204, 200):
            return f"Deleted repository {owner}/{repo}"
        return f"Failed to delete: {res.get('data')}"

    if action in ("create_file", "update_file"):
        owner = params.get("owner") or owner_default
        res = gh_put_file(
            token, owner, params.get("repo", ""), params.get("path", ""),
            params.get("content", ""), params.get("message", "GitHub Agent update"),
            params.get("branch", "main"),
        )
        if res["status"] in (200, 201):
            st.session_state.last_file = params.get("content", "")
            st.session_state.last_name = (params.get("path") or "file").split("/")[-1]
            st.session_state.zip_files[params.get("path", "")] = params.get("content", "")
            return f"Wrote {params.get('path')}"
        return f"Failed: {res.get('data')}"

    if action == "read_file":
        content = gh_get_file(
            token, params.get("owner") or owner_default, params.get("repo", ""),
            params.get("path", ""), params.get("ref", "main"),
        )
        if content is None:
            return "Could not read file."
        st.session_state.last_file = content
        st.session_state.last_name = (params.get("path") or "file").split("/")[-1]
        st.session_state.zip_files[params.get("path", "")] = content
        note = save_markdown_note(
            f"{params.get('repo','repo')}_{(params.get('path') or 'file').replace('/', '_')}",
            f"# {params.get('path')}\n\n```\n{content[:12000]}\n```",
        )
        return f"Read OK. Saved note: `{note.name}`\n\n```\n{content[:3500]}\n```"

    if action == "list_repos":
        repos = gh_list_repos(token)
        lines = [
            f"- **{r['name']}** ({'private' if r.get('private') else 'public'}) — {r['html_url']}"
            for r in repos[:30]
        ]
        return "\n".join(lines) if lines else "No repositories."

    if action == "delete_file":
        owner = params.get("owner") or owner_default
        res = gh_delete_file(
            token, owner, params.get("repo", ""), params.get("path", ""),
            params.get("message", "Delete via GitHub Agent"), params.get("branch", "main"),
        )
        if res["status"] in (200, 204):
            return f"Deleted {params.get('path')}"
        return f"Failed: {res.get('data')}"

    if action == "save_markdown":
        path = save_markdown_note(params.get("filename", "note.md"), params.get("content", ""))
        return f"Saved `{path}`"

    if action == "zip_files":
        files = params.get("files") or st.session_state.zip_files
        if not files:
            return "No files queued."
        st.session_state.zip_files = files
        return f"{len(files)} file(s) ready for ZIP download."

    return params.get("explanation") or f"Unhandled action: {action}"


def enhance_transcript(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    t = re.sub(r"\s+", " ", t)
    fixes = [
        (r"\bgit hub\b", "GitHub"),
        (r"\brepo\b", "repo"),
        (r"\bpublic\b", "public"),
        (r"\bprivate\b", "private"),
    ]
    for pat, rep in fixes:
        t = re.sub(pat, rep, t, flags=re.I)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def voice_panel_html(speak_text: str, auto_speak: bool, rate: float, pitch: float) -> str:
    safe = json.dumps(speak_text or "")
    auto = "true" if auto_speak and speak_text else "false"
    return f"""
<div style="font-family:Inter,system-ui,sans-serif;padding:10px 12px;border-radius:16px;
background:rgba(255,255,255,0.88);border:1px solid rgba(255,255,255,0.65);
box-shadow:0 8px 28px rgba(3,105,161,0.12);">
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">
    <button id="micBtn" style="padding:8px 14px;border-radius:12px;border:1px solid #7dd3fc;
      background:linear-gradient(135deg,#fff,#e0f2fe);color:#0c4a6e;font-weight:700;cursor:pointer;">
      Hold to talk
    </button>
    <button id="stopBtn" style="padding:8px 14px;border-radius:12px;border:1px solid #bae6fd;
      background:#fff;color:#0369a1;font-weight:700;cursor:pointer;">Stop</button>
    <button id="speakBtn" style="padding:8px 14px;border-radius:12px;border:1px solid #bae6fd;
      background:#fff;color:#0369a1;font-weight:700;cursor:pointer;">Speak reply</button>
    <span id="status" style="color:#0c4a6e;font-weight:600;font-size:13px;">Ready</span>
  </div>
  <textarea id="transcript" rows="3" placeholder="Speech appears here. Edit if needed, then Send voice."
    style="width:100%;box-sizing:border-box;border-radius:12px;border:1px solid #7dd3fc;
padding:10px;font-weight:600;color:#0f172a;background:#fff;"></textarea>
  <div style="margin-top:8px;display:flex;gap:8px;">
    <button id="sendBtn" style="padding:8px 16px;border-radius:12px;border:none;
      background:linear-gradient(135deg,#0ea5e9,#0284c7);color:#fff;font-weight:700;cursor:pointer;">
      Send voice
    </button>
  </div>
</div>
<script>
(function() {{
  const status = document.getElementById('status');
  const transcript = document.getElementById('transcript');
  const micBtn = document.getElementById('micBtn');
  const stopBtn = document.getElementById('stopBtn');
  const speakBtn = document.getElementById('speakBtn');
  const sendBtn = document.getElementById('sendBtn');
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  let finalText = '';

  function pickVoice() {{
    const voices = speechSynthesis.getVoices() || [];
    const preferred = voices.find(v => /en(-|_)?(US|GB)/i.test(v.lang) && /neural|natural|premium|google|samantha|aria|jenny/i.test(v.name))
      || voices.find(v => /en(-|_)?(US|GB)/i.test(v.lang))
      || voices[0];
    return preferred || null;
  }}

  function humanize(text) {{
    let t = text || '';
    t = t.replace(/```[\\s\\S]*?```/g, ' code block omitted. ');
    t = t.replace(/\\n+/g, '. ');
    t = t.replace(/\\s+/g, ' ').trim();
    return t.slice(0, 1200);
  }}

  function speak(text) {{
    if (!window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(humanize(text));
    u.rate = {rate};
    u.pitch = {pitch};
    u.volume = 1.0;
    const v = pickVoice();
    if (v) u.voice = v;
    u.onstart = () => status.textContent = 'Speaking...';
    u.onend = () => status.textContent = 'Ready';
    speechSynthesis.speak(u);
  }}

  if (SpeechRecognition) {{
    rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 3;
    rec.lang = 'en-US';
    rec.onstart = () => status.textContent = 'Listening...';
    rec.onerror = (e) => status.textContent = 'Mic: ' + (e.error || 'error');
    rec.onend = () => status.textContent = finalText ? 'Transcript ready' : 'Ready';
    rec.onresult = (event) => {{
      let interim = '';
      let best = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {{
        const res = event.results[i];
        let piece = res[0].transcript;
        if (res.length > 1) {{
          let top = res[0];
          for (let j = 1; j < res.length; j++) {{
            if (res[j].confidence > top.confidence) top = res[j];
          }}
          piece = top.transcript;
        }}
        if (res.isFinal) best += piece + ' ';
        else interim += piece;
      }}
      if (best) finalText += best;
      transcript.value = (finalText + ' ' + interim).trim();
    }};
  }} else {{
    status.textContent = 'Speech recognition not supported in this browser';
  }}

  micBtn.onclick = () => {{
    if (!rec) return;
    finalText = transcript.value ? transcript.value + ' ' : '';
    try {{ rec.start(); }} catch (e) {{ status.textContent = 'Mic busy'; }}
  }};
  stopBtn.onclick = () => {{
    if (rec) try {{ rec.stop(); }} catch (e) {{}}
    speechSynthesis.cancel();
    status.textContent = 'Stopped';
  }};
  speakBtn.onclick = () => speak({safe});
  sendBtn.onclick = () => {{
    const t = (transcript.value || '').trim();
    if (!t) {{ status.textContent = 'Nothing to send'; return; }}
    window.parent.postMessage({{ isStreamlitMessage: true, type: 'streamlit:setComponentValue', value: t }}, '*');
  }};

  if ({auto}) {{
    setTimeout(() => speak({safe}), 400);
  }}
}})();
</script>
"""


def init():
    saved = load_json(SETTINGS)
    defaults = {
        "messages": [],
        "github_token": saved.get("github_token", ""),
        "provider": saved.get("provider", "OpenRouter"),
        "api_key": saved.get("api_key", ""),
        "active_model": saved.get("active_model", ""),
        "fetched_models": saved.get("fetched_models", []),
        "github_user": None,
        "file_expert": saved.get("file_expert", False),
        "voice_enabled": saved.get("voice_enabled", True),
        "auto_speak": saved.get("auto_speak", True),
        "voice_rate": saved.get("voice_rate", 0.95),
        "voice_pitch": saved.get("voice_pitch", 1.0),
        "last_file": None,
        "last_name": None,
        "zip_files": {},
        "pending_voice": None,
        "last_reply_for_tts": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init()

with st.sidebar:
    st.markdown("### GitHub Agent")
    st.caption("Glass UI · voice · repos")

    st.markdown("---")
    st.markdown("**GitHub**")
    tok = st.text_input("Token", type="password", value=st.session_state.github_token, label_visibility="collapsed")
    if tok != st.session_state.github_token:
        st.session_state.github_token = tok
        st.session_state.github_user = None
    if st.session_state.github_token and not st.session_state.github_user:
        u = gh_user(st.session_state.github_token)
        if u:
            st.session_state.github_user = u
            st.success(u.get("login"))
        else:
            st.error("Invalid token")

    st.markdown("---")
    st.markdown("**Provider**")
    plist = list(PROVIDERS.keys())
    pidx = plist.index(st.session_state.provider) if st.session_state.provider in plist else 0
    provider = st.radio("p", plist, index=pidx, horizontal=True, label_visibility="collapsed", key="prov")
    if provider != st.session_state.provider:
        st.session_state.provider = provider
        st.session_state.fetched_models = []
        st.session_state.active_model = ""
        st.rerun()

    if provider == "Gemini":
        st.caption("Google AI Studio API key")
    key = st.text_input("API Key", type="password", value=st.session_state.api_key, label_visibility="collapsed")
    if key != st.session_state.api_key:
        st.session_state.api_key = key
        st.session_state.fetched_models = []

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Fetch Models", use_container_width=True):
            with st.spinner("..."):
                models = fetch_models(provider, st.session_state.api_key)
                st.session_state.fetched_models = models
                st.session_state.active_model = models[0] if models else ""
                st.rerun()
    with b2:
        if st.button("Defaults", use_container_width=True):
            st.session_state.fetched_models = PROVIDERS[provider]["defaults"]
            st.session_state.active_model = st.session_state.fetched_models[0]
            st.rerun()

    models = st.session_state.fetched_models or PROVIDERS[provider]["defaults"]
    if models:
        if st.session_state.active_model not in models:
            st.session_state.active_model = models[0]
        active = st.selectbox(
            "Model", models, index=models.index(st.session_state.active_model),
            label_visibility="collapsed", key="model_box",
        )
        st.session_state.active_model = active
        st.caption(active)
    else:
        st.warning("No models")

    st.markdown("---")
    st.markdown("**Voice**")
    st.session_state.voice_enabled = st.checkbox("Enable voice panel", value=st.session_state.voice_enabled)
    st.session_state.auto_speak = st.checkbox("Auto-speak replies", value=st.session_state.auto_speak)
    st.session_state.voice_rate = st.slider("Speech rate", 0.7, 1.2, float(st.session_state.voice_rate), 0.05)
    st.session_state.voice_pitch = st.slider("Speech pitch", 0.8, 1.2, float(st.session_state.voice_pitch), 0.05)

    st.markdown("---")
    st.session_state.file_expert = st.checkbox("File Expert", value=st.session_state.file_expert)

    if st.button("New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_reply_for_tts = ""
        st.rerun()

    if st.button("Save", use_container_width=True):
        save_json(SETTINGS, {
            "github_token": st.session_state.github_token,
            "provider": st.session_state.provider,
            "api_key": st.session_state.api_key,
            "active_model": st.session_state.active_model,
            "fetched_models": st.session_state.fetched_models,
            "file_expert": st.session_state.file_expert,
            "voice_enabled": st.session_state.voice_enabled,
            "auto_speak": st.session_state.auto_speak,
            "voice_rate": st.session_state.voice_rate,
            "voice_pitch": st.session_state.voice_pitch,
        })
        st.success("Saved")

    if st.button("List repos", use_container_width=True) and st.session_state.github_token:
        repos = gh_list_repos(st.session_state.github_token)
        if repos:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "\n".join([
                    f"- **{r['name']}** ({'private' if r.get('private') else 'public'}) — {r['html_url']}"
                    for r in repos[:25]
                ]),
            })
            st.rerun()

st.markdown("# GitHub Agent")
st.caption("Voice · Gemini · public / private · delete · files")

if st.session_state.voice_enabled:
    voice_val = components.html(
        voice_panel_html(
            st.session_state.last_reply_for_tts,
            st.session_state.auto_speak,
            float(st.session_state.voice_rate),
            float(st.session_state.voice_pitch),
        ),
        height=220,
    )
    if voice_val and isinstance(voice_val, str) and voice_val.strip():
        st.session_state.pending_voice = enhance_transcript(voice_val.strip())

tok_est = sum(tokens(m.get("content", "")) for m in st.session_state.messages)
if tok_est:
    st.caption(f"Context ~ {tok_est} tokens")

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "user" and st.button("Resend", key=f"r_{i}"):
            st.session_state.messages = st.session_state.messages[:i]
            st.session_state["_resend"] = msg["content"]
            st.rerun()

prompt = (
    st.session_state.pop("pending_voice", None)
    or st.chat_input("Message...")
    or st.session_state.pop("_resend", None)
)

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("..."):
            model = st.session_state.active_model
            history = compact([
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[-10:]
            ])
            system = SYSTEM
            if st.session_state.file_expert:
                system += "\nFile Expert mode enabled."

            reply = call_llm(
                st.session_state.provider,
                st.session_state.api_key,
                model,
                history,
                system,
            )
            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.session_state.last_reply_for_tts = reply

            if "```json" in reply and st.session_state.github_token:
                try:
                    js = reply.split("```json")[1].split("```")[0].strip()
                    data = json.loads(js)
                    action = data.get("action", "")
                    params = data.get("params") or {}
                    result = run_action(action, params, st.session_state.github_token, st.session_state.github_user)
                    st.info(result)
                except Exception as e:
                    st.caption(str(e))
    st.rerun()

if st.session_state.last_file:
    st.markdown("---")
    st.code(st.session_state.last_file, language="text")
    st.download_button("Download", data=st.session_state.last_file, file_name=st.session_state.last_name or "file.txt")

if st.session_state.zip_files:
    st.markdown("---")
    st.download_button(
        "Download ZIP",
        data=make_zip(st.session_state.zip_files),
        file_name=f"github-agent-{datetime.now():%Y%m%d-%H%M}.zip",
        mime="application/zip",
    )
