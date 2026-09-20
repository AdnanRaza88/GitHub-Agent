import streamlit as st
import requests
import json
import base64
import io
import zipfile
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
import os

st.set_page_config(
    page_title="GitHub Agent",
    page_icon="https://github.githubassets.com/favicons/favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
.stApp { background: #ffffff; color: #111111; }
section[data-testid="stSidebar"] { background: #f7f7f7; border-right: 1px solid #dddddd; }
section[data-testid="stSidebar"] * { color: #111111 !important; }
h1, h2, h3, h4, h5, h6 { color: #000000 !important; font-weight: 700 !important; }
p, span, label, div { color: #222222; }
.stButton > button { background: #111111; color: #ffffff !important; border: 1px solid #111111; border-radius: 6px; font-weight: 600; padding: 0.45rem 1.1rem; }
.stButton > button:hover { background: #333333; border-color: #333333; }
button[kind="primary"] { background: #000000 !important; color: #ffffff !important; }
.stDownloadButton > button { background: #ffffff; color: #111111 !important; border: 1px solid #111111; border-radius: 6px; font-weight: 600; }
.stDownloadButton > button:hover { background: #f0f0f0; }
[data-testid="stChatMessage"] { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 0.7rem 1rem; margin-bottom: 0.45rem; }
.stTextInput input, .stTextArea textarea { background: #ffffff !important; color: #111111 !important; border: 1px solid #cccccc !important; }
.stRadio label, .stCheckbox label { color: #111111 !important; }
.stCodeBlock, pre { background: #111111 !important; color: #f5f5f5 !important; border-radius: 6px; }
hr { border-color: #dddddd; }
.stCaption, [data-testid="stCaption"] { color: #555555 !important; }
[data-testid="stToolbar"] button, [data-testid="stDecoration"], header[data-testid="stHeader"] { visibility: visible !important; opacity: 1 !important; }
@media (prefers-color-scheme: dark) { .stApp { background: #ffffff !important; color: #111111 !important; } }
footer {visibility: hidden;} #MainMenu {visibility: hidden;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

OPENCODE_ZEN_BASE = "https://opencode.ai/zen/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"

DEFAULT_OPENCODE_FREE = [
    "big-pickle",
    "nemotron-3-ultra-free",
    "mimo-v2.5-free",
    "deepseek-v4-flash-free",
    "nemotron-3.5-lightning-free",
]

DEFAULT_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "qwen/qwen3-32b",
]

SETTINGS_FILE = Path(__file__).parent / "github_agent_settings.json"


def load_settings() -> Dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(data: Dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def init_session():
    saved = load_settings()

    defaults = {
        "messages": [],
        "github_token": saved.get("github_token", ""),
        "provider": saved.get("provider", "OpenCode Zen"),
        "api_key": saved.get("api_key", ""),
        "active_model": saved.get("active_model", ""),
        "selected_models": saved.get("selected_models", []),
        "fetched_models": saved.get("fetched_models", []),
        "last_file_content": None,
        "last_file_name": None,
        "last_files_for_zip": {},
        "github_user": None,
        "file_expert": saved.get("file_expert", False),
        "settings_loaded": True,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def fetch_models(provider: str, api_key: str) -> List[str]:
    if not api_key:
        return []
    try:
        if provider == "OpenCode Zen":
            url = f"{OPENCODE_ZEN_BASE}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                models = []
                items = data.get("data", data) if isinstance(data, dict) else data
                for m in items:
                    if isinstance(m, dict):
                        mid = m.get("id") or m.get("name")
                        if mid:
                            models.append(mid)
                free = [m for m in models if "free" in m.lower() or m in DEFAULT_OPENCODE_FREE or m == "big-pickle"]
                return sorted(set(free or models))[:25]
        else:
            url = f"{GROQ_BASE}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return sorted(models)[:25]
    except Exception:
        pass
    return DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROQ_MODELS


def call_llm(provider: str, api_key: str, model: str, messages: List[Dict], system: str = "") -> str:
    if not api_key or not model:
        return "Please set API key and select a model in the sidebar."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    url = f"{OPENCODE_ZEN_BASE}/chat/completions" if provider == "OpenCode Zen" else f"{GROQ_BASE}/chat/completions"
    body = {
        "model": model,
        "messages": payload_messages,
        "temperature": 0.25,
        "max_tokens": 4096,
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=90)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"API error {r.status_code}: {r.text[:400]}"
    except Exception as e:
        return f"Request failed: {str(e)}"


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


def create_or_update_file(token: str, owner: str, repo: str, path: str, content: str, message: str, branch: str = "main") -> Dict:
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


def get_file_content(token: str, owner: str, repo: str, path: str, ref: str = "main") -> Optional[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=github_headers(token), params={"ref": ref}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def create_repo(token: str, name: str, description: str = "", private: bool = False) -> Dict:
    body = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": True,
    }
    r = requests.post("https://api.github.com/user/repos", headers=github_headers(token), json=body, timeout=20)
    return {"status": r.status_code, "data": r.json() if r.content else {}}


def list_repos(token: str) -> List[Dict]:
    try:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=github_headers(token),
            params={"per_page": 50, "sort": "updated"},
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
    buf.seek(0)
    return buf.read()


SYSTEM_PROMPT = """You are an expert GitHub coding agent. You help users create, read, update and delete repositories, files, branches, issues and pull requests using natural language.

When the user asks to perform an action, respond with a clear plan and then output a structured JSON block that the host application can execute. Use this exact format when an action is needed:

```json
{
  "action": "create_repo|create_file|update_file|read_file|list_repos|delete_file|create_issue|create_pr|zip_files|other",
  "params": { ... },
  "explanation": "short human explanation"
}
```

Supported actions and required params:
- create_repo: name, description (optional), private (bool)
- create_file / update_file: owner, repo, path, content, message, branch (default main)
- read_file: owner, repo, path, ref (optional)
- list_repos: (no params)
- delete_file: owner, repo, path, message, branch
- zip_files: files (dict of path -> content) or list of paths to collect
- other: free-form description

File Expert mode: when enabled, provide deeper multi-file analysis, refactor suggestions, and architecture notes.

Always be concise, professional and safety-conscious. Confirm destructive operations. Prefer free models when discussing cost. Generate complete, production-quality code when asked to write files. Do not use emojis.
"""

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
init_session()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### GitHub Agent")
    st.caption("Black & White · Remote providers only")

    st.markdown("---")
    st.markdown("#### Credentials")

    gh_token = st.text_input(
        "GitHub Personal Access Token",
        type="password",
        value=st.session_state.github_token,
        help="Needs repo scope. Fine-grained tokens preferred.",
        key="gh_token_input",
    )
    if gh_token != st.session_state.github_token:
        st.session_state.github_token = gh_token
        st.session_state.github_user = None

    if st.session_state.github_token and not st.session_state.github_user:
        user = get_github_user(st.session_state.github_token)
        if user:
            st.session_state.github_user = user
            st.success(f"Authenticated as {user.get('login')}")
        else:
            st.error("Invalid token or network error")

    st.markdown("---")
    st.markdown("#### LLM Provider (Remote)")

    provider = st.radio(
        "Provider",
        ["OpenCode Zen", "Groq"],
        index=0 if st.session_state.provider == "OpenCode Zen" else 1,
        horizontal=True,
        key="provider_radio",
    )
    if provider != st.session_state.provider:
        st.session_state.provider = provider
        st.session_state.fetched_models = []
        st.session_state.active_model = ""
        st.session_state.selected_models = []

    api_key = st.text_input(
        f"{provider} API Key",
        type="password",
        value=st.session_state.api_key,
        key="api_key_input",
    )
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        st.session_state.fetched_models = []

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Fetch Models", use_container_width=True):
            with st.spinner("Fetching..."):
                models = fetch_models(provider, st.session_state.api_key)
                st.session_state.fetched_models = models or (
                    DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROQ_MODELS
                )
                if st.session_state.fetched_models and not st.session_state.active_model:
                    st.session_state.active_model = st.session_state.fetched_models[0]
                st.rerun()
    with col2:
        if st.button("Use Defaults", use_container_width=True):
            st.session_state.fetched_models = (
                DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROQ_MODELS
            )
            if st.session_state.fetched_models:
                st.session_state.active_model = st.session_state.fetched_models[0]
            st.rerun()

    models = st.session_state.fetched_models or (
        DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROQ_MODELS
    )

    # ---- FIXED MODEL SELECTION ----
    st.markdown("**Active Model**")
    if models:
        # Ensure active_model is valid
        if st.session_state.active_model not in models:
            st.session_state.active_model = models[0]

        active = st.selectbox(
            "Choose active model",
            options=models,
            index=models.index(st.session_state.active_model) if st.session_state.active_model in models else 0,
            key="active_model_select",
            label_visibility="collapsed",
        )
        st.session_state.active_model = active
        st.caption(f"Currently using: `{active}`")
    else:
        st.warning("No models available. Click Fetch Models or Use Defaults.")

    st.markdown("---")
    st.markdown("#### Modes")
    st.session_state.file_expert = st.checkbox(
        "File Expert mode",
        value=st.session_state.file_expert,
        help="Deeper multi-file analysis and refactor suggestions",
        key="file_expert_cb",
    )

    st.markdown("---")
    st.markdown("#### Persistence")
    st.caption("Save so values survive page refresh.")
    if st.button("Save Settings", use_container_width=True):
        payload = {
            "github_token": st.session_state.github_token,
            "provider": st.session_state.provider,
            "api_key": st.session_state.api_key,
            "active_model": st.session_state.active_model,
            "selected_models": st.session_state.selected_models,
            "fetched_models": st.session_state.fetched_models,
            "file_expert": st.session_state.file_expert,
        }
        if save_settings(payload):
            st.success("Settings saved. They will load after refresh.")
        else:
            st.error("Could not save settings file.")

    if st.button("Clear Saved Settings", use_container_width=True):
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
        st.session_state.github_token = ""
        st.session_state.api_key = ""
        st.session_state.active_model = ""
        st.session_state.fetched_models = []
        st.session_state.github_user = None
        st.success("Saved settings cleared.")
        st.rerun()

    st.markdown("---")
    st.markdown("#### Quick Actions")
    if st.button("List my repos", use_container_width=True) and st.session_state.github_token:
        repos = list_repos(st.session_state.github_token)
        if repos:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Recent repositories:\n\n" + "\n".join(
                    [f"- {r['name']} → {r['html_url']}" for r in repos[:15]]
                )
            })
            st.rerun()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.markdown("# GitHub Agent")
st.markdown(
    '<p style="color:#555555;margin-top:-0.7rem;">Create · Read · Update · Delete repositories and files with natural language</p>',
    unsafe_allow_html=True,
)
st.caption("Use the Streamlit menu (top-right) for System / Light / Dark. Settings can be saved so they survive refresh.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask me to create a repo, write a file, list issues, or prepare a zip..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            model = st.session_state.active_model or (st.session_state.fetched_models[0] if st.session_state.fetched_models else "big-pickle")
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-8:]]

            system = SYSTEM_PROMPT
            if st.session_state.file_expert:
                system += "\n\nFile Expert mode is ON. Provide deeper analysis, multi-file reasoning, and concrete refactor suggestions."

            reply = call_llm(
                st.session_state.provider,
                st.session_state.api_key,
                model,
                history,
                system=system,
            )
            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

            if "```json" in reply and st.session_state.github_token:
                try:
                    json_str = reply.split("```json")[1].split("```")[0].strip()
                    action_data = json.loads(json_str)
                    action = action_data.get("action")
                    params = action_data.get("params", {})

                    if action == "create_repo":
                        res = create_repo(
                            st.session_state.github_token,
                            params.get("name", "new-repo"),
                            params.get("description", ""),
                            params.get("private", False),
                        )
                        if res["status"] in (200, 201):
                            st.success(f"Repository created: {res['data'].get('html_url')}")
                        else:
                            st.error(f"Failed: {res['data']}")

                    elif action in ("create_file", "update_file"):
                        owner = params.get("owner") or (
                            st.session_state.github_user.get("login") if st.session_state.github_user else ""
                        )
                        res = create_or_update_file(
                            st.session_state.github_token,
                            owner,
                            params.get("repo"),
                            params.get("path"),
                            params.get("content", ""),
                            params.get("message", "Update via GitHub Agent"),
                            params.get("branch", "main"),
                        )
                        if res["status"] in (200, 201):
                            st.success(f"File written: {params.get('path')}")
                            content = params.get("content", "")
                            st.session_state.last_file_content = content
                            fname = params.get("path", "file.txt").split("/")[-1]
                            st.session_state.last_file_name = fname
                            st.session_state.last_files_for_zip[params.get("path", fname)] = content
                        else:
                            st.error(f"Failed: {res.get('data')}")

                    elif action == "read_file":
                        content = get_file_content(
                            st.session_state.github_token,
                            params.get("owner"),
                            params.get("repo"),
                            params.get("path"),
                            params.get("ref", "main"),
                        )
                        if content is not None:
                            st.session_state.last_file_content = content
                            fname = params.get("path", "file").split("/")[-1]
                            st.session_state.last_file_name = fname
                            st.session_state.last_files_for_zip[params.get("path", fname)] = content
                            st.code(content[:4000] + ("..." if len(content) > 4000 else ""), language="python")
                        else:
                            st.warning("Could not read file")

                    elif action == "list_repos":
                        repos = list_repos(st.session_state.github_token)
                        st.markdown("\n".join([f"- [{r['name']}]({r['html_url']})" for r in repos[:20]]))

                    elif action == "zip_files":
                        files = params.get("files") or st.session_state.last_files_for_zip
                        if files:
                            st.session_state.last_files_for_zip = files
                            st.success(f"Prepared {len(files)} file(s) for zip download below.")
                        else:
                            st.warning("No files available to zip.")

                except Exception as e:
                    st.caption(f"(Action parser skipped: {e})")

if st.session_state.last_file_content:
    st.markdown("---")
    st.markdown("### Generated / Retrieved File")
    st.code(st.session_state.last_file_content, language="python")
    st.download_button(
        label="Download file",
        data=st.session_state.last_file_content,
        file_name=st.session_state.last_file_name or "file.txt",
        mime="text/plain",
    )

if st.session_state.last_files_for_zip:
    st.markdown("---")
    st.markdown("### Zip Export")
    st.write(f"Files ready: {len(st.session_state.last_files_for_zip)}")
    for path in list(st.session_state.last_files_for_zip.keys())[:10]:
        st.caption(path)
    zip_bytes = make_zip(st.session_state.last_files_for_zip)
    st.download_button(
        label="Download ZIP",
        data=zip_bytes,
        file_name=f"github-agent-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
        mime="application/zip",
    )
    if st.button("Clear zip queue"):
        st.session_state.last_files_for_zip = {}
        st.rerun()

st.markdown("---")
with st.expander("Sandbox / Notes"):
    st.markdown(
        """
        This agent prefers the connected GitHub MCP tools when available.
        For complex multi-step workflows you can extend it with LangGraph.
        Code execution sandbox is not enabled in this version for security.
        Use the File Expert toggle for deeper analysis.
        Settings (including API keys) can be saved locally so they survive page refresh.
        """
    )

st.markdown(
    '<div style="margin-top:2.5rem;text-align:center;color:#888888;font-size:0.8rem;">GitHub Agent · Black & White · Groq + OpenCode Zen · MCP preferred</div>',
    unsafe_allow_html=True,
)
