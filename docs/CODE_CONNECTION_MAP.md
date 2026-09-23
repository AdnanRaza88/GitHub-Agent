# Code Connection Map

Last updated: 2026-09-23 22:20 PKT

## 1. Entry Points
- app.py — Streamlit host (run: streamlit run app.py)

## 2. File Inventory
| Path | Role | Key exports | Depends on | Depended by |
|------|------|-------------|------------|-------------|
| app.py | UI + orchestration + GitHub REST + LLM | PROVIDERS, SYSTEM, run_action, call_llm, compact | requests, streamlit | — |
| aether_settings.json | persisted keys/provider/model | — | app.py load/save | app.py |
| aether_projects.json | project messages + sources | — | app.py | app.py |
| notes/*.md | sandbox markdown notes | save_markdown_note | app.py | user download |
| docs/CODE_CONNECTION_MAP.md | structure map | — | agents | agents |
| requirements.txt | deps | streamlit, requests | — | runtime |

## 3. Import / Call Graph
- app.py is single-file. No internal package imports.
- External: streamlit, requests, stdlib (json, base64, io, zipfile, pathlib, re, datetime)
- Critical functions:
  - call_llm → OpenRouter / Groq / xAI chat completions
  - run_action → gh_* helpers (create_repo, put_file, get_file, delete_file, list_repos, set_visibility)
  - compact → trims chat history near ~5500 tokens
  - fetch_models → provider /models endpoint
  - save_markdown_note → notes/

## 4. Critical Shared Contracts
- Action JSON schema (LLM → host):
  action: create_repo | update_visibility | create_file | update_file | read_file | list_repos | list_tree | delete_file | search_code | review_code | zip_files | save_markdown | other
- session_state keys: messages, github_token, provider, api_key, active_model, fetched_models, projects, current_project, last_file, last_name, zip_files, github_user, file_expert
- Settings file keys: github_token, provider, api_key, active_model, fetched_models, file_expert, current_project
- Default provider: OpenRouter (free models preferred, suffix :free)

## 5. Change Impact Rules
- Changing action names in SYSTEM requires matching branches in run_action.
- Changing PROVIDERS keys requires UI radio options to stay in sync.
- Never rename session_state keys without migration of settings JSON.
- UI and LLM system prompt must both say Aether (no RepoForge / GitHub Agent leftovers).
- No comments and no emojis in production source.

## 6. Recent Changes Log
- 2026-09-23: Bootstrap map; remove module docstring from app.py; brand Aether; enforce no-comments rule.
