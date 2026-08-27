from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .assumption_killer import (
    AssumptionKiller,
    AssumptionKillerFailure,
    NebiusAssumptionKiller,
)
from .competitor_research import (
    CompetitorResearcher,
    CompetitorResearchFailure,
    YouMCPCompetitorResearcher,
)
from .consumer_research import Researcher, ResearchFailure, YouMCPConsumerResearcher
from .extractor import ExtractionFailure, Extractor, NebiusExtractor
from .market_feasibility import (
    MarketFeasibilityFailure,
    MarketFeasibilityResearcher,
    YouMCPMarketFeasibilityResearcher,
)
from .state import BuildOrBustState, REQUIRED_FIELDS


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def build_graph(
    extractor: Extractor,
    researcher: Researcher,
    competitor_researcher: CompetitorResearcher,
    market_feasibility_researcher: MarketFeasibilityResearcher,
    assumption_killer: AssumptionKiller,
    checkpointer: Any,
):
    def intake(state: BuildOrBustState) -> dict[str, Any]:
        raw_input = (state.get("raw_input") or "").strip()
        if not raw_input:
            return {
                "status": "error",
                "error_code": "missing_user_input",
                "error_message": "Please provide a product idea.",
            }
        try:
            data = extractor.extract(raw_input)
        except ExtractionFailure as exc:
            return {"status": "error", "error_code": exc.code, "error_message": str(exc)}

        values = {name: _clean(getattr(data, name)) for name in REQUIRED_FIELDS}
        missing = [name for name, value in values.items() if value is None]
        return {
            **values,
            "missing_fields": missing,
            "status": "needs_clarification" if missing else "ready",
            "error_code": None,
            "error_message": None,
        }

    def route_after_intake(state: BuildOrBustState) -> str:
        if state.get("status") == "needs_clarification":
            return "clarify"
        if state.get("status") == "ready":
            return "research"
        return "done"

    def clarify(state: BuildOrBustState) -> dict[str, Any]:
        missing = state.get("missing_fields", [])
        labels = ", ".join(field.replace("_", " ") for field in missing)
        question = f"Please clarify: {labels}."
        answer = interrupt({"question": question, "missing_fields": missing})
        if not isinstance(answer, str) or not answer.strip():
            return {
                "status": "error",
                "error_code": "missing_user_input",
                "error_message": "Clarification cannot be empty.",
            }
        return {
            "raw_input": f"{state['raw_input']}\nAdditional clarification: {answer.strip()}",
            "clarification_question": question,
            "status": "pending",
        }

    def consumer_research(state: BuildOrBustState) -> dict[str, Any]:
        try:
            report, sources = researcher.research(state)
        except ResearchFailure as exc:
            return {
                "status": "error",
                "error_code": "consumer_research_failure",
                "error_message": str(exc),
            }
        return {
            "consumer_research": report.model_dump(),
            "research_sources": sources,
            "status": "research_complete",
            "error_code": None,
            "error_message": None,
        }

    def competitor_research(state: BuildOrBustState) -> dict[str, Any]:
        try:
            report, sources = competitor_researcher.research(state)
        except CompetitorResearchFailure as exc:
            return {
                "status": "error",
                "error_code": "competitor_research_failure",
                "error_message": str(exc),
            }
        return {
            "competitor_research": report.model_dump(),
            "competitor_sources": sources,
            "status": "competitor_research_complete",
            "error_code": None,
            "error_message": None,
        }

    def route_after_consumer_research(state: BuildOrBustState) -> str:
        if state.get("status") == "research_complete":
            return "competitors"
        return "done"

    def market_feasibility_research(state: BuildOrBustState) -> dict[str, Any]:
        try:
            report, sources = market_feasibility_researcher.research(state)
        except MarketFeasibilityFailure as exc:
            return {
                "status": "error",
                "error_code": "market_feasibility_failure",
                "error_message": str(exc),
            }
        return {
            "market_feasibility_research": report.model_dump(),
            "market_feasibility_sources": sources,
            "status": "market_feasibility_complete",
            "error_code": None,
            "error_message": None,
        }

    def route_after_competitor_research(state: BuildOrBustState) -> str:
        if state.get("status") == "competitor_research_complete":
            return "market_feasibility"
        return "done"

    def assumption_analysis(state: BuildOrBustState) -> dict[str, Any]:
        try:
            report = assumption_killer.analyze(state)
        except AssumptionKillerFailure as exc:
            return {
                "status": "error",
                "error_code": exc.code,
                "error_message": str(exc),
            }
        return {
            "assumption_analysis": report.model_dump(),
            "status": "assumption_analysis_complete",
            "error_code": None,
            "error_message": None,
        }

    def route_after_market_feasibility(state: BuildOrBustState) -> str:
        if state.get("status") == "market_feasibility_complete":
            return "assumptions"
        return "done"

    builder = StateGraph(BuildOrBustState)
    builder.add_node("intake", intake)
    builder.add_node("clarify", clarify)
    builder.add_node("consumer_research", consumer_research)
    builder.add_node("competitor_research", competitor_research)
    builder.add_node("market_feasibility_research", market_feasibility_research)
    builder.add_node("assumption_analysis", assumption_analysis)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges(
        "intake",
        route_after_intake,
        {"clarify": "clarify", "research": "consumer_research", "done": END},
    )
    builder.add_edge("clarify", "intake")
    builder.add_conditional_edges(
        "consumer_research",
        route_after_consumer_research,
        {"competitors": "competitor_research", "done": END},
    )
    builder.add_conditional_edges(
        "competitor_research",
        route_after_competitor_research,
        {"market_feasibility": "market_feasibility_research", "done": END},
    )
    builder.add_conditional_edges(
        "market_feasibility_research",
        route_after_market_feasibility,
        {"assumptions": "assumption_analysis", "done": END},
    )
    builder.add_edge("assumption_analysis", END)
    return builder.compile(checkpointer=checkpointer)


@contextmanager
def open_graph(
    db_path: str = "build_or_bust.db",
    extractor: Extractor | None = None,
    researcher: Researcher | None = None,
    competitor_researcher: CompetitorResearcher | None = None,
    market_feasibility_researcher: MarketFeasibilityResearcher | None = None,
    assumption_killer: AssumptionKiller | None = None,
) -> Iterator[Any]:
    connection = sqlite3.connect(db_path, check_same_thread=False)
    try:
        yield build_graph(
            extractor or NebiusExtractor(),
            researcher or YouMCPConsumerResearcher(),
            competitor_researcher or YouMCPCompetitorResearcher(),
            market_feasibility_researcher or YouMCPMarketFeasibilityResearcher(),
            assumption_killer or NebiusAssumptionKiller(),
            SqliteSaver(connection),
        )
    finally:
        connection.close()
