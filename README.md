# GitHub Agent

Black-and-white Streamlit coding agent for GitHub. Create, read, update and delete repositories and files using natural language.

## Features

- **Providers (remote only)**
  - **Groq** — `https://api.groq.com/openai/v1`
  - **OpenCode Zen** — `https://opencode.ai/zen/v1` (free models supported)
- Model selection with checkboxes
- GitHub Personal Access Token authentication
- Prefers connected GitHub MCP tools
- Full CRUD on repos and files
- File Expert mode for deeper analysis
- Single-file download + ZIP export
- Pure black-and-white light theme (high contrast)
- Explicit support for System / Light / Dark theme switcher visibility
- No emojis in the UI

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

1. Paste your GitHub PAT (needs `repo` scope) in the sidebar.
2. Choose **OpenCode Zen** or **Groq** and paste the API key.
3. Click **Fetch Models** (or Use Defaults) and select models via checkboxes.
4. Optionally enable **File Expert mode**.
5. Chat naturally.

## Security

- Tokens and API keys stay in Streamlit session state only.
- Never commit real tokens.
- Prefer fine-grained GitHub tokens.

## License

MIT
