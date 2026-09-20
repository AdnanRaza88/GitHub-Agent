# GitHub Agent

A beautiful, light-themed Streamlit coding agent that lets you create, read, update and delete GitHub repositories and files using natural language.

## Features

- **Two LLM providers**
  - **Grok** (xAI) — `https://api.x.ai/v1`
  - **OpenCode Zen** — `https://opencode.ai/zen/v1` (free models supported)
- Model selection with checkboxes (free models preferred for OpenCode Zen)
- GitHub Personal Access Token authentication
- Full CRUD:
  - Create repositories
  - Create / update / read files
  - List repositories
  - More actions via natural language
- In-app code viewer + download button for generated files
- Professional light UI following color-theory principles (cool neutrals + soft teal accent)

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

1. Paste your **GitHub PAT** (needs `repo` scope) in the sidebar.
2. Choose **OpenCode Zen** or **Grok** and paste the corresponding API key.
3. Click **Fetch Models** (or Use Defaults) and select the models you want.
4. Chat naturally:  
   - “Create a new public repo called my-awesome-project”  
   - “Write a Python hello-world file in that repo”  
   - “List my recent repositories”

## Security Notes

- Tokens and API keys stay in Streamlit session state only.
- Never commit real tokens.
- Prefer fine-grained GitHub tokens with the least privilege required.

## License

MIT
