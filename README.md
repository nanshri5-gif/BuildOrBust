# Build or Bust — Stages 1–5

The workflow turns a raw product idea into validated shared state. If required
facts are absent, execution pauses for a human answer and resumes from a SQLite
checkpoint. Once intake is complete, Consumer Research, Competitor Research, and
Market and Feasibility Research nodes use OpenAI web search to collect evidence.
The Assumption Killer then challenges the idea using only those saved reports.

This intentionally does not include Judge or Recommendation agents.

## Setup

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Put your OpenAI API key in `.env`, then run. Stages 2, 3, and 4 each perform a
billed OpenAI web-search request after intake is complete. Stage 5 performs one
additional structured model call without web search:

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
- `competitor_research.py` researches direct competitors, alternatives, and pricing.
- `market_feasibility.py` researches demand signals and implementation feasibility.
- `assumption_killer.py` challenges critical assumptions using saved evidence only.
- `graph.py` routes intake, clarification, research, and assumption analysis.
- `cli.py` starts or resumes a run.
- `tests/test_stage1.py` covers all five stages with fake API collaborators.
