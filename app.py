import streamlit as st
import requests
import json
import base64
from datetime import datetime
from typing import Optional, List, Dict, Any
import os

# ---------------------------------------------------------------------------
# Page config & light theme (color theory: cool neutrals + soft teal accent)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="GitHub Agent",
    page_icon="🐙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Professional light palette (60-30-10)
# Dominant: soft off-white / cool gray
# Secondary: clean white surfaces
# Accent: soft teal / cyan for actions
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* Main background */
.stApp {
    background: linear-gradient(160deg, #f8fafc 0%, #f1f5f9 40%, #eef2ff 100%);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(12px);
    border-right: 1px solid #e2e8f0;
}

/* Cards / containers */
div[data-testid="stVerticalBlock"] > div {
    border-radius: 12px;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #0d9488 0%, #0891b2 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 1.2rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(13, 148, 136, 0.25);
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(13, 148, 136, 0.35);
}

/* Primary button variant */
button[kind="primary"] {
    background: linear-gradient(135deg, #0f766e 0%, #0e7490 100%) !important;
}

/* Chat messages */
[data-testid="stChatMessage"] {
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
}

/* Headers */
h1, h2, h3 {
    color: #0f172a !important;
    font-weight: 700 !important;
}

/* Subtle glass panels */
.glass-panel {
    background: rgba(255, 255, 255, 0.65);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(226, 232, 240, 0.8);
    border-radius: 16px;
    padding: 1.25rem;
    box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
}

/* Code viewer */
.code-block {
    background: #0f172a;
    color: #e2e8f0;
    border-radius: 10px;
    padding: 1rem;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.85rem;
    overflow-x: auto;
}

/* Status badges */
.badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-success { background: #ccfbf1; color: #0f766e; }
.badge-info { background: #e0f2fe; color: #0369a1; }
.badge-warn { background: #fef3c7; color: #b45309; }

/* Hide Streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OPENCODE_ZEN_BASE = "https://opencode.ai/zen/v1"
GROK_BASE = "https://api.x.ai/v1"

DEFAULT_OPENCODE_FREE = [
    "big-pickle",
    "nemotron-3-ultra-free",
    "mimo-v2.5-free",
    "deepseek-v4-flash-free",
    "nemotron-3.5-lightning-free",
]

DEFAULT_GROK_MODELS = [
    "grok-4",
    "grok-3",
    "grok-2",
    "grok-beta",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def init_session():
    defaults = {
        "messages": [],
        "github_token": "",
        "provider": "OpenCode Zen",
        "api_key": "",
        "selected_models": [],
        "fetched_models": [],
        "last_file_content": None,
        "last_file_name": None,
        "github_user": None,
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
                models = [m.get("id") or m.get("name") for m in data.get("data", data) if isinstance(m, dict)]
                free = [m for m in models if "free" in m.lower() or m in DEFAULT_OPENCODE_FREE or m == "big-pickle"]
                return sorted(set(free or models))[:20]
        else:  # Grok
            url = f"{GROK_BASE}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return sorted(models)[:15]
    except Exception:
        pass
    return DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROK_MODELS


def call_llm(provider: str, api_key: str, model: str, messages: List[Dict], system: str = "") -> str:
    if not api_key or not model:
        return "⚠️ Please set API key and select a model in the sidebar."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    if provider == "OpenCode Zen":
        url = f"{OPENCODE_ZEN_BASE}/chat/completions"
        body = {
            "model": model,
            "messages": payload_messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }
    else:
        url = f"{GROK_BASE}/chat/completions"
        body = {
            "model": model,
            "messages": payload_messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=90)
        if r.status_code == 200:
            data = r.json()
            return data["choices"][0]["message"]["content"]
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
    # Check if exists
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
        r = requests.get("https://api.github.com/user/repos", headers=github_headers(token), params={"per_page": 50, "sort": "updated"}, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# System prompt for the coding agent
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert GitHub coding agent. You help users create, read, update and delete repositories, files, branches, issues and pull requests using natural language.

When the user asks to perform an action, respond with a clear plan and then output a structured JSON block that the host application can execute. Use this exact format when an action is needed:

```json
{
  "action": "create_repo|create_file|update_file|read_file|list_repos|delete_file|create_issue|create_pr|other",
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
- other: free-form description

Always be concise, professional and safety-conscious. Confirm destructive operations. Prefer free models when discussing cost. Generate complete, production-quality code when asked to write files.
"""

# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
init_session()

# Sidebar
with st.sidebar:
    st.markdown("### 🐙 GitHub Agent")
    st.caption("Light • Fast • Beautiful")

    st.markdown("---")
    st.markdown("#### 🔑 Credentials")

    gh_token = st.text_input(
        "GitHub Personal Access Token",
        type="password",
        value=st.session_state.github_token,
        help="Needs `repo` scope. Fine-grained tokens preferred.",
        key="gh_token_input",
    )
    if gh_token != st.session_state.github_token:
        st.session_state.github_token = gh_token
        st.session_state.github_user = None

    if st.session_state.github_token and not st.session_state.github_user:
        user = get_github_user(st.session_state.github_token)
        if user:
            st.session_state.github_user = user
            st.success(f"Authenticated as **{user.get('login')}**")
        else:
            st.error("Invalid token or network error")

    st.markdown("---")
    st.markdown("#### 🤖 LLM Provider")

    provider = st.radio(
        "Choose provider",
        ["OpenCode Zen", "Grok"],
        index=0 if st.session_state.provider == "OpenCode Zen" else 1,
        horizontal=True,
    )
    st.session_state.provider = provider

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
                    DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROK_MODELS
                )
    with col2:
        if st.button("Use Defaults", use_container_width=True):
            st.session_state.fetched_models = (
                DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROK_MODELS
            )

    models = st.session_state.fetched_models or (
        DEFAULT_OPENCODE_FREE if provider == "OpenCode Zen" else DEFAULT_GROK_MODELS
    )

    st.markdown("**Select models** (checkboxes)")
    selected = []
    for m in models:
        if st.checkbox(m, value=m in st.session_state.selected_models or m == models[0], key=f"model_{m}"):
            selected.append(m)
    st.session_state.selected_models = selected

    if selected:
        st.caption(f"Active: `{selected[0]}`")
    else:
        st.warning("Select at least one model")

    st.markdown("---")
    st.markdown("#### Quick Actions")
    if st.button("List my repos", use_container_width=True) and st.session_state.github_token:
        repos = list_repos(st.session_state.github_token)
        if repos:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Here are your recent repositories:\n\n" + "\n".join(
                    [f"- **{r['name']}** → {r['html_url']}" for r in repos[:15]]
                )
            })
            st.rerun()

# Main area
st.markdown("# GitHub Agent")
st.markdown(
    '<p style="color:#64748b;margin-top:-0.8rem;">Create • Read • Update • Delete repositories & files with natural language</p>',
    unsafe_allow_html=True,
)

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask me to create a repo, write a file, list issues..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            model = (st.session_state.selected_models or ["big-pickle"])[0]
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-8:]]
            reply = call_llm(
                st.session_state.provider,
                st.session_state.api_key,
                model,
                history,
                system=SYSTEM_PROMPT,
            )
            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

            # Very lightweight action parser (look for JSON block)
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
                        res = create_or_update_file(
                            st.session_state.github_token,
                            params.get("owner", st.session_state.github_user.get("login") if st.session_state.github_user else ""),
                            params.get("repo"),
                            params.get("path"),
                            params.get("content", ""),
                            params.get("message", "Update via GitHub Agent"),
                            params.get("branch", "main"),
                        )
                        if res["status"] in (200, 201):
                            st.success(f"File written: {params.get('path')}")
                            st.session_state.last_file_content = params.get("content")
                            st.session_state.last_file_name = params.get("path", "file.txt").split("/")[-1]
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
                            st.session_state.last_file_name = params.get("path", "file").split("/")[-1]
                            st.code(content[:3000] + ("..." if len(content) > 3000 else ""), language="python")
                        else:
                            st.warning("Could not read file")

                    elif action == "list_repos":
                        repos = list_repos(st.session_state.github_token)
                        st.markdown("\n".join([f"- [{r['name']}]({r['html_url']})" for r in repos[:20]]))

                except Exception as e:
                    st.caption(f"(Action parser skipped: {e})")

# File viewer + download
if st.session_state.last_file_content:
    st.markdown("---")
    st.markdown("### 📄 Generated / Retrieved File")
    st.code(st.session_state.last_file_content, language="python")
    st.download_button(
        label="⬇️ Download file",
        data=st.session_state.last_file_content,
        file_name=st.session_state.last_file_name or "file.txt",
        mime="text/plain",
        use_container_width=False,
    )

# Footer
st.markdown(
    """
    <div style="margin-top:3rem;text-align:center;color:#94a3b8;font-size:0.8rem;">
        Built with ❤️ • Light theme • Color theory applied • Powered by Grok & OpenCode Zen
    </div>
    """,
    unsafe_allow_html=True,
)
