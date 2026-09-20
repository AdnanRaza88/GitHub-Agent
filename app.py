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
    page_title="GitHub Agent",
    page_icon="https://github.githubassets.com/favicons/favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
.stApp { background: linear-gradient(165deg, #f0f9ff 0%, #e0f2fe 45%, #f0f9ff 100%); color: #0c4a6e; }
section[data-testid="stSidebar"] { background: rgba(255,255,255,0.88); backdrop-filter: blur(12px); border-right: 1px solid #bae6fd; }
section[data-testid="stSidebar"] * { color: #0c4a6e !important; }
h1, h2, h3, h4, h5, h6 { color: #0369a1 !important; font-weight: 700 !important; }
p, span, label, div { color: #0c4a6e; }
.stButton > button {
    background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
    color: #ffffff !important; border: none; border-radius: 8px; font-weight: 600;
    padding: 0.5rem 1.2rem; box-shadow: 0 2px 10px rgba(14,165,233,0.35);
}
.stButton > button:hover {
    background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
    box-shadow: 0 4px 16px rgba(14,165,233,0.45); transform: translateY(-1px);
}
button[kind="primary"] { background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important; color: #fff !important; }
.stDownloadButton > button {
    background: #ffffff; color: #0284c7 !important; border: 1.5px solid #0ea5e9;
    border-radius: 8px; font-weight: 600;
}
.stDownloadButton > button:hover { background: #e0f2fe; }
[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.8); border: 1px solid #bae6fd; border-radius: 12px;
    padding: 0.75rem 1rem; margin-bottom: 0.5rem; box-shadow: 0 2px 8px rgba(14,165,233,0.08);
}
.stTextInput input, .stTextArea textarea {
    background: #ffffff !important; color: #0c4a6e !important;
    border: 1px solid #7dd3fc !important; border-radius: 8px !important;
}
.stRadio label, .stCheckbox label { color: #0c4a6e !important; }
.stCodeBlock, pre { background: #0c4a6e !important; color: #e0f2fe !important; border-radius: 8px; }
hr { border-color: #bae6fd; }
.stCaption, [data-testid="stCaption"] { color: #0369a1 !important; }
[data-testid="stToolbar"] button, [data-testid="stDecoration"], header[data-testid="stHeader"] {
    visibility: visible !important; opacity: 1 !important;
}
footer { visibility: hidden; } #MainMenu { visibility: hidden; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

PROVIDERS = {
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "qwen/qwen3-32b",
        ],
        "note": "Fast free tier. Good for coding.",
    },
    "Grok (xAI)": {
        "base_url": "https://api.x.ai/v1",
        "default_models": [
            "grok-4",
            "grok-3",
            "grok-2",
            "grok-beta",
        ],
        "note": "xAI Grok models. Requires xAI API key.",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_models": [
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "qwen/qwen-2.5-7b-instruct:free",
            "microsoft/phi-3-mini-128k-instruct:free",
            "meta-llama/llama-3.3-70b-instruct",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o-mini",
        ],
        "note": "Many free models available (look for :free). Good fallback.",
    },
}

SETTINGS_FILE = Path(__file__).parent / "github_agent_settings.json"

def load_settings() -> Dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_settings(data: Dict) -> bool:
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
        "provider": saved.get("provider", "Groq"),
        "api_key": saved.get("api_key", ""),
        "active_model": saved.get("active_model", ""),
        "fetched_models": saved.get("fetched_models", []),
        "last_file_content": None,
        "last_file_name": None,
        "last_files_for_zip": {},
        "github_user": None,
        "file_expert": saved.get("file_expert", False),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def get_provider_cfg(name: str) -> Dict:
    return PROVIDERS.get(name, PROVIDERS["Groq"])

def fetch_models(provider: str, api_key: str) -> List[str]:
    if not api_key:
        return get_provider_cfg(provider)["default_models"]
    cfg = get_provider_cfg(provider)
    try:
        r = requests.get(
            f"{cfg['base_url']}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            models = []
            for m in data.get("data", []):
                mid = m.get("id")
                if mid:
                    models.append(mid)
            if models:
                if provider == "OpenRouter":
                    free = [m for m in models if ":free" in m]
                    paid = [m for m in models if ":free" not in m]
                    return (sorted(free) + sorted(paid))[:40]
                return sorted(models)[:40]
    except Exception:
        pass
    return cfg["default_models"]

def call_llm(provider: str, api_key: str, model: str, messages: List[Dict], system: str = "") -> str:
    if not api_key:
        return "Please enter a valid API key in the sidebar."
    if not model:
        return "Please select a model in the sidebar."

    cfg = get_provider_cfg(provider)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "OpenRouter":
        headers["HTTP-Referer"] = "https://github.com/AdnanRaza88/GitHub-Agent"
        headers["X-Title"] = "GitHub Agent"

    payload = []
    if system:
        payload.append({"role": "system", "content": system})
    payload.extend(messages)

    body = {
        "model": model,
        "messages": payload,
        "temperature": 0.25,
        "max_tokens": 4096,
    }

    try:
        r = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers=headers,
            json=body,
            timeout=90,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]

        if r.status_code == 401:
            return (
                "**Invalid API Key (401)**\n\n"
                f"The key for **{provider}** is invalid or expired.\n\n"
                "- Double-check you copied the full key.\n"
                "- Generate a new key from the provider dashboard.\n"
                "- Make sure there are no extra spaces."
            )
        if r.status_code == 403:
            if "FreeTierError" in r.text or "free tier" in r.text.lower():
                return (
                    "**Free Tier Restriction**\n\n"
                    f"{provider} free models cannot be used from external apps.\n\n"
                    "Switch to **Groq** or **OpenRouter** (they have working free models)."
                )
            return f"**Access Denied (403)**\n\n{r.text[:400]}"
        return f"API error {r.status_code}: {r.text[:500]}"
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
        if r.status_code == 200:
            data = r.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
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
    buf.seek(0)
    return buf.read()

SYSTEM_PROMPT = """You are GitHub Agent, a precise coding assistant that works with GitHub repositories.

When the user asks to perform an action, reply with a short plan and then a JSON block the host can execute:

```json
{
  "action": "create_repo|create_file|update_file|read_file|list_repos|delete_file|zip_files|other",
  "params": {},
  "explanation": "short explanation"
}
```

Supported actions:
- create_repo: name, description (optional), private (bool)
- create_file / update_file: owner, repo, path, content, message, branch
- read_file: owner, repo, path, ref
- list_repos: (no params)
- delete_file: owner, repo, path, message, branch
- zip_files: files dict
- other: free description

Be concise. Confirm destructive actions. Produce complete, clean code. Never use emojis.
"""

init_session()

with st.sidebar:
    st.markdown("### GitHub Agent")
    st.caption("Sky Blue · Clean · Fast")

    st.markdown("---")
    st.markdown("#### Credentials")

    gh_token = st.text_input(
        "GitHub Personal Access Token",
        type="password",
        value=st.session_state.github_token,
        help="Needs repo scope. Prefer fine-grained tokens.",
        key="gh_token_input",
    )
    if gh_token != st.session_state.github_token:
        st.session_state.github_token = gh_token
        st.session_state.github_user = None

    if st.session_state.github_token and not st.session_state.github_user:
        user = get_github_user(st.session_state.github_token)
        if user:
            st.session_state.github_user = user
            st.success(f"Signed in as {user.get('login')}")
        else:
            st.error("Invalid GitHub token")

    st.markdown("---")
    st.markdown("#### Provider")

    provider_list = list(PROVIDERS.keys())
    current_idx = provider_list.index(st.session_state.provider) if st.session_state.provider in provider_list else 0
    provider = st.radio(
        "Choose provider",
        provider_list,
        index=current_idx,
        horizontal=True,
        key="provider_radio",
    )
    if provider != st.session_state.provider:
        st.session_state.provider = provider
        st.session_state.fetched_models = []
        st.session_state.active_model = ""

    st.caption(get_provider_cfg(provider)["note"])

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
            with st.spinner("Loading models..."):
                models = fetch_models(provider, st.session_state.api_key)
                st.session_state.fetched_models = models
                if models and not st.session_state.active_model:
                    st.session_state.active_model = models[0]
                st.rerun()
    with col2:
        if st.button("Use Defaults", use_container_width=True):
            st.session_state.fetched_models = get_provider_cfg(provider)["default_models"]
            st.session_state.active_model = st.session_state.fetched_models[0]
            st.rerun()

    models = st.session_state.fetched_models or get_provider_cfg(provider)["default_models"]

    st.markdown("**Active Model**")
    if models:
        if st.session_state.active_model not in models:
            st.session_state.active_model = models[0]
        active = st.selectbox(
            "Model",
            options=models,
            index=models.index(st.session_state.active_model),
            key="active_model_select",
            label_visibility="collapsed",
        )
        st.session_state.active_model = active
        st.caption(f"Using: `{active}`")
    else:
        st.warning("No models loaded.")

    st.markdown("---")
    st.markdown("#### Options")
    st.session_state.file_expert = st.checkbox(
        "File Expert mode",
        value=st.session_state.file_expert,
        help="Deeper multi-file analysis",
        key="file_expert_cb",
    )

    st.markdown("---")
    st.markdown("#### Save Settings")
    st.caption("Keeps keys and model after refresh.")
    if st.button("Save Settings", use_container_width=True):
        ok = save_settings({
            "github_token": st.session_state.github_token,
            "provider": st.session_state.provider,
            "api_key": st.session_state.api_key,
            "active_model": st.session_state.active_model,
            "fetched_models": st.session_state.fetched_models,
            "file_expert": st.session_state.file_expert,
        })
        if ok:
            st.success("Saved.")
        else:
            st.error("Save failed.")

    if st.button("Clear Saved", use_container_width=True):
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
        for key in ["github_token", "api_key", "active_model", "fetched_models", "github_user"]:
            st.session_state[key] = "" if key != "fetched_models" else []
        st.session_state.github_user = None
        st.success("Cleared.")
        st.rerun()

    st.markdown("---")
    if st.button("List my repos", use_container_width=True) and st.session_state.github_token:
        repos = list_repos(st.session_state.github_token)
        if repos:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Recent repositories:\n\n" + "\n".join(
                    [f"- **{r['name']}** → {r['html_url']}" for r in repos[:20]]
                )
            })
            st.rerun()

st.markdown("# GitHub Agent")
st.markdown(
    '<p style="color:#0369a1;margin-top:-0.6rem;font-size:1.05rem;">Create, read, update and delete GitHub repositories with natural language.</p>',
    unsafe_allow_html=True,
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask anything about your repos..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            model = st.session_state.active_model or get_provider_cfg(st.session_state.provider)["default_models"][0]
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-8:]]
            system = SYSTEM_PROMPT
            if st.session_state.file_expert:
                system += "\nFile Expert mode is ON. Give deeper analysis and concrete suggestions."
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
                            st.success(f"Created: {res['data'].get('html_url')}")
                        else:
                            st.error(str(res.get("data")))

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
                            fname = (params.get("path") or "file.txt").split("/")[-1]
                            st.session_state.last_file_name = fname
                            st.session_state.last_files_for_zip[params.get("path", fname)] = content
                        else:
                            st.error(str(res.get("data")))

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
                            fname = (params.get("path") or "file").split("/")[-1]
                            st.session_state.last_file_name = fname
                            st.session_state.last_files_for_zip[params.get("path", fname)] = content
                            st.code(content[:4000] + ("..." if len(content) > 4000 else ""), language="text")
                        else:
                            st.warning("Could not read file")

                    elif action == "list_repos":
                        repos = list_repos(st.session_state.github_token)
                        st.markdown("\n".join([f"- [{r['name']}]({r['html_url']})" for r in repos[:25]]))

                    elif action == "zip_files":
                        files = params.get("files") or st.session_state.last_files_for_zip
                        if files:
                            st.session_state.last_files_for_zip = files
                            st.success(f"Ready to download {len(files)} file(s).")
                        else:
                            st.warning("No files to zip.")

                except Exception as e:
                    st.caption(f"(Action parser: {e})")

if st.session_state.last_file_content:
    st.markdown("---")
    st.markdown("### File Preview")
    st.code(st.session_state.last_file_content, language="text")
    st.download_button(
        "Download file",
        data=st.session_state.last_file_content,
        file_name=st.session_state.last_file_name or "file.txt",
        mime="text/plain",
    )

if st.session_state.last_files_for_zip:
    st.markdown("---")
    st.markdown("### Zip Export")
    st.write(f"{len(st.session_state.last_files_for_zip)} file(s) ready")
    zip_bytes = make_zip(st.session_state.last_files_for_zip)
    st.download_button(
        "Download ZIP",
        data=zip_bytes,
        file_name=f"github-agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
        mime="application/zip",
    )
    if st.button("Clear zip queue"):
        st.session_state.last_files_for_zip = {}
        st.rerun()

st.markdown("---")
with st.expander("Notes"):
    st.markdown(
        """
- **Groq** — best free option for this app right now.
- **OpenRouter** — many free models (names end with `:free`).
- **Grok (xAI)** — requires a valid xAI API key.
- OpenCode Zen free tier is blocked for external apps.
- Click **Save Settings** so keys and model survive page refresh.
        """
    )

st.markdown(
    '<div style="margin-top:2rem;text-align:center;color:#0284c7;font-size:0.8rem;">GitHub Agent · Sky Blue · Groq · Grok · OpenRouter</div>',
    unsafe_allow_html=True,
)
