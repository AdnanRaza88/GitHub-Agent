# GitHub Agent

Streamlit app for GitHub with natural language. Glassmorphism sky-blue UI.

## Features

- Create repositories (public or private)
- Change visibility (public ↔ private)
- Delete repositories
- Create, update, read, delete files
- List repos, ZIP export, File Expert mode
- Providers: OpenRouter, Groq, Grok (xAI)

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

1. Paste GitHub PAT (repo scope).
2. Choose provider and API key.
3. Fetch Models, pick a model (prefer OpenRouter `:free`).
4. Chat: e.g. make repo X private, delete repo Y (confirm first).

## Structure

See `docs/CODE_CONNECTION_MAP.md`.

## License

MIT
