# Code Connection Map

Last updated: 2026-09-24 18:10 PKT

## 1. Entry Points
- app.py — Streamlit host (streamlit run app.py)

## 2. File Inventory
| Path | Role | Key exports | Depends on | Depended by |
|------|------|-------------|------------|-------------|
| app.py | UI + LLM + GitHub REST | PROVIDERS, SYSTEM, run_action, call_llm, gh_delete_repo | requests, streamlit | — |
| github_agent_settings.json | persisted keys | — | app.py | app.py |
| notes/*.md | sandbox notes | save_markdown_note | app.py | user |
| docs/CODE_CONNECTION_MAP.md | structure map | — | agents | agents |
| requirements.txt | deps | streamlit, requests | — | runtime |

## 3. Import / Call Graph
- Single-file app
- call_llm → OpenRouter / Groq / xAI
- run_action → create_repo, update_visibility, delete_repo, put_file, get_file, delete_file, list_repos
- compact → history near 5500 tokens

## 4. Critical Shared Contracts
- Actions: create_repo | update_visibility | delete_repo | create_file | update_file | read_file | list_repos | delete_file | zip_files | save_markdown | other
- Brand: GitHub Agent
- Theme: shiny blue glassmorphism; white on blue; bold black (#0f172a) on white/glass panels
- No comments, no emojis

## 5. Change Impact Rules
- SYSTEM action names must match run_action
- delete_repo requires confirm in agent replies
- Visibility via update_visibility private bool

## 6. Recent Changes Log
- 2026-09-24: Glassmorphism UI; delete_repo; keep public/private; name GitHub Agent
