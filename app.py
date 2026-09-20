import streamlit as st
import requests
import json
import base64
import io
import zipfile
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

st.set_page_config(
    page_title="RepoForge",
    page_icon="https://github.githubassets.com/favicons/favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
.stApp { background: linear-gradient(165deg, #f0f9ff 0%, #e0f2fe 50%, #f8fafc 100%); color: #0c4a6e; }
section[data-testid="stSidebar"] { background: rgba(255,255,255,0.92); border-right: 1px solid #bae6fd; }
section[data-testid="stSidebar"] * { color: #0c4a6e !important; }
h1, h2, h3 { color: #0c4a6e !important; font-weight: 700 !important; letter-spacing: -0.02em; }
.stButton > button {
    background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
    color: #fff !important; border: none; border-radius: 8px; font-weight: 600;
    padding: 0.45rem 1.1rem; box-shadow: 0 2px 8px rgba(14,165,233,0.25);
}
.stButton > button:hover { background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); }
.stDownloadButton > button {
    background: #fff; color: #0284c7 !important; border: 1.5px solid #0ea5e9; border-radius: 8px; font-weight: 600;
}
[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.9); border: 1px solid #e0f2fe; border-radius: 12px;
    padding: 0.75rem 1rem; margin-bottom: 0.5rem;
}
.stTextInput input, .stTextArea textarea {
    background: #fff !important; color: #0c4a6e !important; border: 1px solid #7dd3fc !important; border-radius: 8px !important;
}
.stCodeBlock, pre { background: #0c4a6e !important; color: #e0f2fe !important; border-radius: 8px; }
hr { border-color: #e0f2fe; }
.stCaption { color: #0369a1 !important; }
footer, #MainMenu { visibility: hidden; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

PROVIDERS = {
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_models": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "openai/gpt-oss-20b:free",
            "openai/gpt-oss-120b:free",
            "qwen/qwen3-coder:free",
            "google/gemma-2-9b-it:free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "nvidia/nemotron-nano-9b-v2:free",
        ],
        "note": "Free models end with :free. Recommended.",
    },
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
        ],
        "note": "Always click Fetch Models — only use what your key returns.",
    },
    "Grok (xAI)": {
        "base_url": "https://api.x.ai/v1",
        "default_models": ["grok-4", "grok-3", "grok-2"],
        "note": "Requires xAI API key from console.x.ai",
    },
}

SETTINGS_FILE = Path(__file__).parent / "repoforge_settings.json"
PROJECTS_FILE = Path(__file__).parent / "repoforge_projects.json"


def load_json(path: Path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default if default is not None else {}


def save_json(path: Path, data) -> bool:
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def approx_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def init_session():
    saved = load_json(SETTINGS_FILE)
    projects = load_json(PROJECTS_FILE, {})

    defaults = {
        "messages": [],
        "github_token": saved.get("github_token", ""),
        "provider": saved.get("provider", "OpenRouter"),
        "api_key": saved.get("api_key", ""),
        "active_model": saved.get("active_model", ""),
        "fetched_models": saved.get("fetched_models", []),
        "last_file_content": None,
        "last_file_name": None,
        "last_files_for_zip": {},
        "github_user": None,
        "file_expert": saved.get("file_expert", False),
        "projects": projects if projects else {"default": {"messages": [], "sources": []}},
        "current_project": saved.get("current_project", "default"),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.current_project not in st.session_state.projects:
        st.session_state.projects[st.session_state.current_project] = {"messages": [], "sources": []}


def get_cfg(name: str) -> Dict:
    return PROVIDERS.get(name, PROVIDERS["OpenRouter"])


def fetch_models(provider: str, api_key: str) -> List[str]:
    cfg = get_cfg(provider)
    if not api_key:
        return cfg["default_models"]
    try:
        r = requests.get(
            f"{cfg['base_url']}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", []) if m.get("id")]
            if not models:
                return cfg["default_models"]
            if provider == "OpenRouter":
                free = sorted([m for m in models if m.endswith(":free")])
                paid = sorted([m for m in models if not m.endswith(":free")])
                return (free + paid)[:60]
            return sorted(models)[:60]
    except Exception:
        pass
    return cfg["default_models"]


def call_llm(provider: str, api_key: str, model: str, messages: List[Dict], system: str = "") -> str:
    if not api_key:
        return "Enter a valid API key in the sidebar."
    if not model:
        return "Select a model. Click **Fetch Models** first."

    cfg = get_cfg(provider)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "OpenRouter":
        headers["HTTP-Referer"] = "https://github.com/AdnanRaza88/GitHub-Agent"
        headers["X-Title"] = "RepoForge"

    payload = []
    if system:
        payload.append({"role": "system", "content": system})
    payload.extend(messages)

    try:
        r = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers=headers,
            json={"model": model, "messages": payload, "temperature": 0.2, "max_tokens": 4096},
            timeout=90,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]

        body = r.text[:700]
        if r.status_code == 401:
            return f"**Invalid API key** for {provider}. Generate a new key and paste it again."
        if r.status_code == 404:
            if "unavailable for free" in body or ":free" in model:
                return (
                    f"**This free model is no longer available.**\n\n"
                    f"Model `{model}` was discontinued or moved to paid.\n\n"
                    "Click **Fetch Models** to load the current free list, then pick a model that still ends with `:free`."
                )
            return (
                f"**Model not found / no access**\n\n`{model}`\n\n"
                "Click **Fetch Models** and select one from the updated list."
            )
        if r.status_code == 403:
            return f"**Access denied (403)**\n\n{body}"
        return f"Error {r.status_code}: {body}"
    except Exception as e:
        return f"Request failed: {e}"


def compact_messages(messages: List[Dict], limit: int = 5500) -> List[Dict]:
    total = sum(approx_tokens(m.get("content", "")) for m in messages)
    if total < limit or len(messages) <= 6:
        return messages
    recent = messages[-6:]
    older = messages[:-6]
    summary = "Previous context:\n" + "\n".join(
        f"{m.get('role')}: {(m.get('content') or '')[:180]}" for m in older[-6:]
    )
    return [{"role": "system", "content": summary}] + recent


def github_headers(token: str) -> Dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_github_user(token: str) -> Optional[Dict]:
    try:
        r = requests.get("https://api.github.com/user", headers=github_headers(token), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def create_or_update_file(token, owner, repo, path, content, message, branch="main") -> Dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    sha = None
    try:
        r = requests.get(url, headers=github_headers(token), params={"ref": branch}, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass
    body = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=github_headers(token), json=body, timeout=20)
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def get_file_content(token, owner, repo, path, ref="main") -> Optional[str]:
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=github_headers(token),
            params={"ref": ref},
            timeout=15,
        )
        if r.status_code == 200 and r.json().get("encoding") == "base64":
            return base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def create_repo(token, name, description="", private=False) -> Dict:
    r = requests.post(
        "https://api.github.com/user/repos",
        headers=github_headers(token),
        json={"name": name, "description": description, "private": private, "auto_init": True},
        timeout=20,
    )
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def list_repos(token) -> List[Dict]:
    try:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=github_headers(token),
            params={"per_page": 100, "sort": "updated"},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def make_zip(files: Dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


SYSTEM_PROMPT = """You are RepoForge, a professional GitHub coding agent.

When an action is required, output a short plan followed by this JSON:

```json
{
  "action": "create_repo|create_file|update_file|read_file|list_repos|delete_file|zip_files|other",
  "params": {},
  "explanation": "brief"
}
```

Supported actions:
- create_repo: name, description?, private?
- create_file / update_file: owner, repo, path, content, message, branch
- read_file: owner, repo, path, ref
- list_repos
- delete_file: owner, repo, path, message, branch
- zip_files
- other

Be precise and concise. Confirm destructive operations. Produce complete, production-quality code. No emojis.
"""

# ---------- Init ----------
init_session()
proj = st.session_state.current_project
st.session_state.messages = st.session_state.projects[proj].get("messages", [])

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### RepoForge")
    st.caption("Professional GitHub agent")

    st.markdown("---")
    st.markdown("**Project**")
    names = list(st.session_state.projects.keys())
    sel = st.selectbox("Active", names, index=names.index(proj) if proj in names else 0, label_visibility="collapsed")
    if sel != st.session_state.current_project:
        st.session_state.projects[st.session_state.current_project]["messages"] = st.session_state.messages
        st.session_state.current_project = sel
        st.session_state.messages = st.session_state.projects[sel].get("messages", [])
        st.rerun()

    new_name = st.text_input("New project", placeholder="project-name", label_visibility="collapsed")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Create", use_container_width=True) and new_name.strip():
            n = new_name.strip()
            if n not in st.session_state.projects:
                st.session_state.projects[st.session_state.current_project]["messages"] = st.session_state.messages
                st.session_state.projects[n] = {"messages": [], "sources": []}
                st.session_state.current_project = n
                st.session_state.messages = []
                save_json(PROJECTS_FILE, st.session_state.projects)
                st.rerun()
    with c2:
        if st.button("New chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.projects[st.session_state.current_project]["messages"] = []
            st.rerun()

    with st.expander("Sources"):
        src = st.text_area("Add context / notes", height=70, label_visibility="collapsed")
        if st.button("Add source") and src.strip():
            st.session_state.projects[st.session_state.current_project].setdefault("sources", []).append(src.strip())
            save_json(PROJECTS_FILE, st.session_state.projects)
            st.success("Added")

    st.markdown("---")
    st.markdown("**GitHub**")
    gh = st.text_input("Token", type="password", value=st.session_state.github_token, label_visibility="collapsed")
    if gh != st.session_state.github_token:
        st.session_state.github_token = gh
        st.session_state.github_user = None
    if st.session_state.github_token and not st.session_state.github_user:
        u = get_github_user(st.session_state.github_token)
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

    st.caption(get_cfg(provider)["note"])

    key = st.text_input("API Key", type="password", value=st.session_state.api_key, label_visibility="collapsed")
    if key != st.session_state.api_key:
        st.session_state.api_key = key
        st.session_state.fetched_models = []

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Fetch Models", use_container_width=True):
            with st.spinner("…"):
                models = fetch_models(provider, st.session_state.api_key)
                st.session_state.fetched_models = models
                st.session_state.active_model = models[0] if models else ""
                st.rerun()
    with b2:
        if st.button("Defaults", use_container_width=True):
            st.session_state.fetched_models = get_cfg(provider)["default_models"]
            st.session_state.active_model = st.session_state.fetched_models[0]
            st.rerun()

    models = st.session_state.fetched_models or get_cfg(provider)["default_models"]

    if not models:
        st.warning("No models")
        active_model = ""
    else:
        if st.session_state.active_model not in models:
            st.session_state.active_model = models[0]
        active_model = st.selectbox(
            "Model",
            models,
            index=models.index(st.session_state.active_model),
            label_visibility="collapsed",
            key="model_box",
        )
        st.session_state.active_model = active_model
        st.caption(active_model)

    st.markdown("---")
    st.session_state.file_expert = st.checkbox("File Expert", value=st.session_state.file_expert)

    if st.button("Save", use_container_width=True):
        save_json(SETTINGS_FILE, {
            "github_token": st.session_state.github_token,
            "provider": st.session_state.provider,
            "api_key": st.session_state.api_key,
            "active_model": st.session_state.active_model,
            "fetched_models": st.session_state.fetched_models,
            "file_expert": st.session_state.file_expert,
            "current_project": st.session_state.current_project,
        })
        save_json(PROJECTS_FILE, st.session_state.projects)
        st.success("Saved")

    if st.button("List repos", use_container_width=True) and st.session_state.github_token:
        repos = list_repos(st.session_state.github_token)
        if repos:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "\n".join([f"- **{r['name']}** — {r['html_url']}" for r in repos[:25]])
            })
            st.session_state.projects[st.session_state.current_project]["messages"] = st.session_state.messages
            st.rerun()

# ---------- Main ----------
st.markdown("# RepoForge")
st.caption(f"Project · {st.session_state.current_project}")

tok = sum(approx_tokens(m.get("content", "")) for m in st.session_state.messages)
if tok > 0:
    st.caption(f"Context ≈ {tok} tokens")

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "user":
            if st.button("Resend", key=f"r_{i}"):
                st.session_state.messages = st.session_state.messages[:i]
                st.session_state.projects[st.session_state.current_project]["messages"] = st.session_state.messages
                st.session_state["_resend"] = msg["content"]
                st.rerun()

prompt = st.chat_input("Message…") or st.session_state.pop("_resend", None)

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("…"):
            model = st.session_state.active_model
            history = compact_messages(
                [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-10:]]
            )
            system = SYSTEM_PROMPT
            if st.session_state.file_expert:
                system += "\nFile Expert mode enabled."
            srcs = st.session_state.projects[st.session_state.current_project].get("sources", [])
            if srcs:
                system += "\n\nProject sources:\n" + "\n---\n".join(srcs[-4:])

            reply = call_llm(
                st.session_state.provider,
                st.session_state.api_key,
                model,
                history,
                system=system,
            )
            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.session_state.projects[st.session_state.current_project]["messages"] = st.session_state.messages

            if "```json" in reply and st.session_state.github_token:
                try:
                    js = reply.split("```json")[1].split("```")[0].strip()
                    data = json.loads(js)
                    action = data.get("action")
                    p = data.get("params", {})

                    if action == "create_repo":
                        res = create_repo(st.session_state.github_token, p.get("name", "new-repo"), p.get("description", ""), p.get("private", False))
                        st.success(res["data"].get("html_url")) if res["status"] in (200, 201) else st.error(str(res.get("data")))
                    elif action in ("create_file", "update_file"):
                        owner = p.get("owner") or (st.session_state.github_user or {}).get("login", "")
                        res = create_or_update_file(st.session_state.github_token, owner, p.get("repo"), p.get("path"), p.get("content", ""), p.get("message", "RepoForge"), p.get("branch", "main"))
                        if res["status"] in (200, 201):
                            st.success(p.get("path"))
                            st.session_state.last_file_content = p.get("content", "")
                            st.session_state.last_file_name = (p.get("path") or "file").split("/")[-1]
                            st.session_state.last_files_for_zip[p.get("path", "")] = st.session_state.last_file_content
                        else:
                            st.error(str(res.get("data")))
                    elif action == "read_file":
                        content = get_file_content(st.session_state.github_token, p.get("owner"), p.get("repo"), p.get("path"), p.get("ref", "main"))
                        if content:
                            st.session_state.last_file_content = content
                            st.code(content[:3500], language="text")
                    elif action == "list_repos":
                        repos = list_repos(st.session_state.github_token)
                        st.markdown("\n".join(f"- [{r['name']}]({r['html_url']})" for r in repos[:20]))
                except Exception as e:
                    st.caption(str(e))

if st.session_state.last_file_content:
    st.markdown("---")
    st.code(st.session_state.last_file_content, language="text")
    st.download_button("Download", data=st.session_state.last_file_content, file_name=st.session_state.last_file_name or "file.txt")

if st.session_state.last_files_for_zip:
    st.markdown("---")
    st.download_button("Download ZIP", data=make_zip(st.session_state.last_files_for_zip), file_name=f"export-{datetime.now():%Y%m%d-%H%M}.zip", mime="application/zip")
