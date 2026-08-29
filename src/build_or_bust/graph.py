from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
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
from .evidence_gate import EvidenceGate
from .judge import Judge, JudgeFailure, NebiusJudge
from .idea_registry import IdeaRegistry, IdeaRegistryFailure, SQLiteIdeaRegistry
from .market_feasibility import (
    MarketFeasibilityFailure,
    MarketFeasibilityResearcher,
    YouMCPMarketFeasibilityResearcher,
)
from .recommendation import (
    NebiusRecommendationAgent,
    RecommendationAgent,
    RecommendationFailure,
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
    judge: Judge,
    checkpointer: Any,
    recommendation_agent: RecommendationAgent | None = None,
    evidence_gate: EvidenceGate | None = None,
    idea_registry: IdeaRegistry | None = None,
):
    gate = evidence_gate or EvidenceGate()

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
            return "prior_lookup" if idea_registry is not None else "research"
        return "done"

    def prior_idea_lookup(state: BuildOrBustState) -> dict[str, Any]:
        if idea_registry is None:
            return {"status": "no_prior_evaluation"}
        try:
            match = idea_registry.find_recent(state)
        except IdeaRegistryFailure as exc:
            return {
                "status": "error",
                "error_code": "idea_registry_failure",
                "error_message": str(exc),
            }
        if match is None:
            return {"status": "no_prior_evaluation", "prior_evaluation": None}
        return {
            "status": "prior_evaluation_found",
            "prior_evaluation": match.model_dump(),
        }

    def route_after_prior_lookup(state: BuildOrBustState) -> str:
        if state.get("status") == "no_prior_evaluation":
            return "research"
        if state.get("status") == "prior_evaluation_found":
            return "choose"
        return "done"

    def choose_prior_evaluation(state: BuildOrBustState) -> dict[str, Any]:
        prior = state.get("prior_evaluation") or {}
        response = interrupt(
            {
                "kind": "prior_evaluation",
                "question": "A fresh completed evaluation matches this idea. Reuse it or refresh research?",
                "choices": ["reuse", "refresh"],
                "decision": prior.get("decision"),
                "review_action": prior.get("review_action"),
                "created_at": prior.get("created_at"),
                "original_thread_id": prior.get("original_thread_id"),
            }
        )
        if not isinstance(response, dict):
            return {
                "status": "error",
                "error_code": "invalid_prior_evaluation_response",
                "error_message": "Prior-evaluation choice must be reuse or refresh.",
            }
        action = str(response.get("action") or "").strip().lower()
        if action == "refresh":
            return {"status": "ready_for_research"}
        if action == "reuse":
            snapshot = prior.get("snapshot")
            if not isinstance(snapshot, dict):
                return {
                    "status": "error",
                    "error_code": "idea_registry_failure",
                    "error_message": "The prior evaluation snapshot is malformed.",
                }
            return {
                **snapshot,
                "status": "evaluation_reused",
                "reused_from_evaluation_id": prior.get("evaluation_id"),
                "evaluation_saved": False,
            }
        return {
            "status": "error",
            "error_code": "invalid_prior_evaluation_response",
            "error_message": "Prior-evaluation choice must be reuse or refresh.",
        }

    def route_after_prior_choice(state: BuildOrBustState) -> str:
        if state.get("status") == "ready_for_research":
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
            return "evidence_gate"
        return "done"

    def assess_evidence(state: BuildOrBustState) -> dict[str, Any]:
        assessment = gate.assess(state)
        return {
            "evidence_assessment": assessment.model_dump(),
            "status": (
                "evidence_sufficient"
                if assessment.sufficient
                else "insufficient_evidence"
            ),
        }

    def route_after_evidence_gate(state: BuildOrBustState) -> str:
        if state.get("status") == "evidence_sufficient":
            return "assumptions"
        return "done"

    def judgment(state: BuildOrBustState) -> dict[str, Any]:
        try:
            result = judge.decide(state)
        except JudgeFailure as exc:
            return {
                "status": "error",
                "error_code": exc.code,
                "error_message": str(exc),
            }
        return {
            "judgment": result.model_dump(),
            "status": "judgment_complete",
            "error_code": None,
            "error_message": None,
        }

    def route_after_assumption_analysis(state: BuildOrBustState) -> str:
        if state.get("status") == "assumption_analysis_complete":
            return "judge"
        return "done"

    def recommendation(state: BuildOrBustState) -> dict[str, Any]:
        if recommendation_agent is None:
            raise RuntimeError("Recommendation node requires a recommendation agent.")
        try:
            result = recommendation_agent.recommend(state)
        except RecommendationFailure as exc:
            return {
                "status": "error",
                "error_code": exc.code,
                "error_message": str(exc),
            }
        return {
            "recommendation": result.model_dump(),
            "status": "recommendation_complete",
            "error_code": None,
            "error_message": None,
        }

    def human_review(state: BuildOrBustState) -> dict[str, Any]:
        response = interrupt(
            {
                "kind": "human_review",
                "question": "Review the recommendation: approve, revise, or reject?",
                "choices": ["approve", "revise", "reject"],
                "revision_count": state.get("recommendation_revision_count", 0),
                "max_revisions": 2,
            }
        )
        if not isinstance(response, dict):
            return {
                "status": "error",
                "error_code": "invalid_review_response",
                "error_message": "Review must include an action and optional notes.",
            }
        action = str(response.get("action") or "").strip().lower()
        notes = str(response.get("notes") or "").strip()
        if action not in {"approve", "revise", "reject"}:
            return {
                "status": "error",
                "error_code": "invalid_review_response",
                "error_message": "Review action must be approve, revise, or reject.",
            }
        revision_count = state.get("recommendation_revision_count", 0)
        history = [
            *state.get("review_history", []),
            {
                "action": action,
                "notes": notes,
                "revision_count": revision_count,
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
        ]
        if action == "revise":
            if not notes:
                return {
                    "status": "error",
                    "error_code": "review_feedback_required",
                    "error_message": "Revision feedback cannot be empty.",
                }
            if revision_count >= 2:
                return {
                    "status": "error",
                    "error_code": "revision_limit_reached",
                    "error_message": "The recommendation revision limit has been reached.",
                    "review_history": history,
                }
            return {
                "status": "revision_requested",
                "review_action": action,
                "review_notes": notes,
                "review_feedback": notes,
                "recommendation_revision_count": revision_count + 1,
                "review_history": history,
            }
        return {
            "status": "review_complete",
            "review_action": action,
            "review_notes": notes,
            "review_feedback": None,
            "recommendation_revision_count": revision_count,
            "review_history": history,
        }

    def route_after_human_review(state: BuildOrBustState) -> str:
        if state.get("status") == "revision_requested":
            return "revise"
        if state.get("status") == "review_complete" and idea_registry is not None:
            return "persist"
        return "done"

    def persist_evaluation(state: BuildOrBustState) -> dict[str, Any]:
        if idea_registry is None:
            return {"status": "review_complete"}
        try:
            evaluation_id = idea_registry.save(state)
        except IdeaRegistryFailure as exc:
            return {
                "status": "error",
                "error_code": "idea_registry_failure",
                "error_message": str(exc),
            }
        return {
            "status": "review_complete",
            "evaluation_id": evaluation_id,
            "evaluation_saved": True,
        }

    builder = StateGraph(BuildOrBustState)
    builder.add_node("intake", intake)
    builder.add_node("clarify", clarify)
    builder.add_node("prior_idea_lookup", prior_idea_lookup)
    builder.add_node("choose_prior_evaluation", choose_prior_evaluation)
    builder.add_node("consumer_research", consumer_research)
    builder.add_node("competitor_research", competitor_research)
    builder.add_node("market_feasibility_research", market_feasibility_research)
    builder.add_node("evidence_gate", assess_evidence)
    builder.add_node("assumption_analysis", assumption_analysis)
    builder.add_node("judgment", judgment)
    if recommendation_agent is not None:
        builder.add_node("recommendation", recommendation)
        builder.add_node("human_review", human_review)
        if idea_registry is not None:
            builder.add_node("persist_evaluation", persist_evaluation)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "clarify": "clarify",
            "prior_lookup": "prior_idea_lookup",
            "research": "consumer_research",
            "done": END,
        },
    )
    builder.add_edge("clarify", "intake")
    builder.add_conditional_edges(
        "prior_idea_lookup",
        route_after_prior_lookup,
        {
            "research": "consumer_research",
            "choose": "choose_prior_evaluation",
            "done": END,
        },
    )
    builder.add_conditional_edges(
        "choose_prior_evaluation",
        route_after_prior_choice,
        {"research": "consumer_research", "done": END},
    )
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
        {"evidence_gate": "evidence_gate", "done": END},
    )
    builder.add_conditional_edges(
        "evidence_gate",
        route_after_evidence_gate,
        {"assumptions": "assumption_analysis", "done": END},
    )
    builder.add_conditional_edges(
        "assumption_analysis",
        route_after_assumption_analysis,
        {"judge": "judgment", "done": END},
    )
    if recommendation_agent is not None:
        builder.add_edge("judgment", "recommendation")
        builder.add_edge("recommendation", "human_review")
        builder.add_conditional_edges(
            "human_review",
            route_after_human_review,
            {
                "revise": "recommendation",
                "persist": "persist_evaluation" if idea_registry is not None else END,
                "done": END,
            },
        )
        if idea_registry is not None:
            builder.add_edge("persist_evaluation", END)
    else:
        builder.add_edge("judgment", END)
    return builder.compile(checkpointer=checkpointer)


@contextmanager
def open_graph(
    db_path: str = "build_or_bust.db",
    extractor: Extractor | None = None,
    researcher: Researcher | None = None,
    competitor_researcher: CompetitorResearcher | None = None,
    market_feasibility_researcher: MarketFeasibilityResearcher | None = None,
    assumption_killer: AssumptionKiller | None = None,
    judge: Judge | None = None,
    recommendation_agent: RecommendationAgent | None = None,
    idea_registry: IdeaRegistry | None = None,
) -> Iterator[Any]:
    connection = sqlite3.connect(db_path, check_same_thread=False)
    try:
        yield build_graph(
            extractor or NebiusExtractor(),
            researcher or YouMCPConsumerResearcher(),
            competitor_researcher or YouMCPCompetitorResearcher(),
            market_feasibility_researcher or YouMCPMarketFeasibilityResearcher(),
            assumption_killer or NebiusAssumptionKiller(),
            judge or NebiusJudge(),
            SqliteSaver(connection),
            recommendation_agent=recommendation_agent or NebiusRecommendationAgent(),
            idea_registry=idea_registry or SQLiteIdeaRegistry(db_path),
        )
    finally:
        connection.close()
