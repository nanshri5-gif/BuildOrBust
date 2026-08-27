# Build or Bust — Stages 1–5

The workflow turns a raw product idea into validated shared state. If required
facts are absent, execution pauses for a human answer and resumes from a SQLite
checkpoint. Once intake is complete, Consumer, Competitor, and Market and
Feasibility Research use You.com tools through MCP.
The Assumption Killer then challenges the idea using only those saved reports.
Intake and clarification use Nebius Token Factory with JSON-schema output.

This intentionally does not include Judge or Recommendation agents.

## Setup

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Put your Nebius API key in `.env`, and set `NEBIUS_MODEL` to a Nebius model
marked as supporting JSON mode. Add `YDC_API_KEY` for authenticated You.com
MCP access; without it, Consumer Research uses You.com's limited free search
profile, but Competitor page extraction and Market Research are unavailable.
The Assumption Killer performs one structured Nebius model call:

```powershell
build-or-bust "A mobile app that helps busy US parents plan weeknight meals"
```

If it asks a question, copy the displayed thread ID and resume it:

```powershell
build-or-bust --thread YOUR_THREAD_ID --resume "The first market is Canada"
```

The same thread ID is essential: LangGraph uses it to find the saved checkpoint.
Run `pytest` to verify the error, resume, and research paths without calling live APIs.

## Files

- `state.py` defines the single shared state contract.
- `extractor.py` calls Nebius chat completions and validates JSON with Pydantic.
- `consumer_research.py` calls You.com through MCP, then uses Nebius to validate a focused consumer report.
- `competitor_research.py` uses MCP search and page extraction for competitors and pricing.
- `market_feasibility.py` uses MCP structured research for demand and feasibility evidence.
- `assumption_killer.py` uses Nebius to challenge assumptions from saved evidence only.
- `graph.py` routes intake, clarification, research, and assumption analysis.
- `cli.py` starts or resumes a run.
- `tests/test_stage1.py` covers all five stages with fake API collaborators.
