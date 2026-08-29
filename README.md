# Build or Bust — Stages 1–9

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
The Recommendation Agent preserves that decision and converts it into constrained,
measurable next actions for human review.
The graph then pauses for a human to approve, revise, or reject the recommendation.
Revision feedback regenerates only the recommendation, never the Judge's decision,
and the workflow permits at most two revision cycles.
Approved and rejected evaluations are saved in application-owned SQLite tables.
After intake, a fresh exact fingerprint match pauses before research and asks whether
to reuse the completed evaluation or refresh all research. Matches expire after 90 days;
failed, incomplete, and insufficient-evidence runs are never registered.

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

After reviewing the recommendation, resume the same thread with one choice:

```powershell
build-or-bust --thread YOUR_THREAD_ID --review approve --notes "Proceed"
build-or-bust --thread YOUR_THREAD_ID --review revise --notes "Use a cheaper one-week test"
build-or-bust --thread YOUR_THREAD_ID --review reject --notes "Risk is too high"
```

When an exact prior evaluation is found, choose one path:

```powershell
build-or-bust --thread YOUR_THREAD_ID --prior reuse
build-or-bust --thread YOUR_THREAD_ID --prior refresh
```

The same thread ID is essential: LangGraph uses it to find the saved checkpoint.
Run `pytest` to verify the error, resume, and research paths without calling live APIs.

## Local UI

Install the updated dependencies, then start the Streamlit interface:

```powershell
pip install -e ".[dev]"
streamlit run src/build_or_bust/ui.py
```

The UI accepts a product idea, resumes clarification and prior-evaluation choices,
shows research and sources, charts deterministic evidence readiness beside the
Judge's separately reported confidence, and supports approve/revise/reject review.
After submission, the page URL contains the LangGraph thread ID. Reopening a URL
such as `http://localhost:8501/?thread=THREAD_ID` restores the saved checkpoint,
including pending interrupts, without rerunning research APIs.

## Public cohort demo

The repository is ready for Streamlit Community Cloud. Public-demo mode hides the
shared evaluation-history sidebar and disables cross-visitor idea lookup and reuse.
LangGraph thread checkpoints remain available while the deployed instance is running,
but Community Cloud does not guarantee that the local SQLite file will survive an app
restart or redeploy.

1. Push this repository to GitHub.
2. Sign in at `https://share.streamlit.io` and create an app from the repository.
3. Set the entrypoint to `src/build_or_bust/ui.py` and select Python 3.13.
4. Open Advanced settings and paste secrets using
   `.streamlit/secrets.toml.example` as the template. Replace both API-key placeholders.
5. Deploy and share the resulting `streamlit.app` URL.

Do not commit `.env` or `.streamlit/secrets.toml`. Both are ignored by Git. Configure
Nebius and You.com spending or request limits before sharing the public URL because
each new evaluation makes paid external API calls. For durable checkpoints and history,
replace local SQLite with a hosted database before treating this as a production app.

To preview the public behavior locally, add this to `.env` and restart Streamlit:

```text
PUBLIC_DEMO_MODE=true
```

## Files

- `state.py` defines the single shared state contract.
- `extractor.py` calls Nebius chat completions and validates JSON with Pydantic.
- `consumer_research.py` calls You.com through MCP, then uses Nebius to validate a focused consumer report.
- `competitor_research.py` uses MCP search and page extraction for competitors and pricing.
- `market_feasibility.py` uses MCP structured research for demand and feasibility evidence.
- `evidence_gate.py` makes the deterministic answerability decision before generation.
- `assumption_killer.py` uses Nebius to challenge assumptions from saved evidence only.
- `judge.py` uses Nebius to make one evidence-grounded decision without new research.
- `recommendation.py` converts the saved decision into experiments and scoped next actions.
- `idea_registry.py` stores completed evaluations, sources, and reviews and performs fresh exact-match lookup.
- `graph.py` routes prior-idea lookup, research, evidence checks, judgment, recommendation, and human review.
- `cli.py` starts or resumes a run.
- `tests/test_stage1.py` covers all nine stages with fake API collaborators.
