from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .consumer_research import OpenAIConsumerResearcher, Researcher, ResearchFailure
from .extractor import ExtractionFailure, Extractor, OpenAIExtractor
from .state import BuildOrBustState, REQUIRED_FIELDS


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def build_graph(extractor: Extractor, researcher: Researcher, checkpointer: Any):
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

    builder = StateGraph(BuildOrBustState)
    builder.add_node("intake", intake)
    builder.add_node("clarify", clarify)
    builder.add_node("consumer_research", consumer_research)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges(
        "intake",
        route_after_intake,
        {"clarify": "clarify", "research": "consumer_research", "done": END},
    )
    builder.add_edge("clarify", "intake")
    builder.add_edge("consumer_research", END)
    return builder.compile(checkpointer=checkpointer)


@contextmanager
def open_graph(
    db_path: str = "build_or_bust.db",
    extractor: Extractor | None = None,
    researcher: Researcher | None = None,
) -> Iterator[Any]:
    connection = sqlite3.connect(db_path, check_same_thread=False)
    try:
        yield build_graph(
            extractor or OpenAIExtractor(),
            researcher or OpenAIConsumerResearcher(),
            SqliteSaver(connection),
        )
    finally:
        connection.close()
