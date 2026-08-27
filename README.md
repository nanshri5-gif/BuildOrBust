# Build or Bust — Stages 1–6

The workflow turns a raw product idea into validated shared state. If required
facts are absent, execution pauses for a human answer and resumes from a SQLite
checkpoint. Once intake is complete, Consumer, Competitor, and Market and
Feasibility Research use You.com tools through MCP.
Before generation continues, a deterministic Evidence Gate checks valid source
counts, independent domains, required research coverage, and successful competitor
page extraction. Weak support stops as `INSUFFICIENT_EVIDENCE`; it is not treated
as a `VALIDATE` decision. The Assumption Killer then challenges sufficiently
supported ideas using only the saved reports.
Intake and clarification use Nebius Token Factory with JSON-schema output.
The Judge evaluates the saved evidence and returns BUILD, VALIDATE, PIVOT, or BUST.

This intentionally does not include a Recommendation agent.

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
- `evidence_gate.py` makes the deterministic answerability decision before generation.
- `assumption_killer.py` uses Nebius to challenge assumptions from saved evidence only.
- `judge.py` uses Nebius to make one evidence-grounded decision without new research.
- `graph.py` routes intake, clarification, research, the evidence gate, assumption analysis, and judgment.
- `cli.py` starts or resumes a run.
- `tests/test_stage1.py` covers all six stages with fake API collaborators.
