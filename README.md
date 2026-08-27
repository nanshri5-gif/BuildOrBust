# Build or Bust — Stages 1–2

The workflow turns a raw product idea into validated shared state. If required
facts are absent, execution pauses for a human answer and resumes from a SQLite
checkpoint. Once intake is complete, a single Consumer Research node uses OpenAI
web search to collect sourced pain points and current behaviors.

This intentionally does not include competitor, market, technical, judge, or
recommendation agents.

## Setup

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Put your OpenAI API key in `.env`, then run. Stage 2 performs a billed OpenAI web
search call after intake is complete:

```powershell
build-or-bust "A mobile app that helps busy US parents plan weeknight meals"
```

If it asks a question, copy the displayed thread ID and resume it:

```powershell
build-or-bust --thread YOUR_THREAD_ID --resume "The first market is Canada"
```

The same thread ID is essential: LangGraph uses it to find the saved checkpoint.
Run `pytest` to verify the error, resume, and research paths without calling OpenAI.

## Files

- `state.py` defines the single shared state contract.
- `extractor.py` calls the OpenAI Responses API with Pydantic structured output.
- `consumer_research.py` runs focused web research and captures returned sources.
- `graph.py` contains intake, human clarification, and consumer research routing.
- `cli.py` starts or resumes a run.
- `tests/test_stage1.py` covers intake and research with fake API collaborators.
