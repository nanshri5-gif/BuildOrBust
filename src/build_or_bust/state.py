from typing import Any, Literal, TypedDict


REQUIRED_FIELDS = (
    "product_idea",
    "target_customer",
    "geography",
    "problem",
    "product_type",
)


class BuildOrBustState(TypedDict, total=False):
    """The shared state that later stages can extend without changing Stage 1."""

    raw_input: str
    product_idea: str | None
    target_customer: str | None
    geography: str | None
    problem: str | None
    product_type: str | None
    missing_fields: list[str]
    clarification_question: str | None
    consumer_research: dict[str, Any] | None
    research_sources: list[dict[str, Any]]
    competitor_research: dict[str, Any] | None
    competitor_sources: list[dict[str, Any]]
    market_feasibility_research: dict[str, Any] | None
    market_feasibility_sources: list[dict[str, Any]]
    evidence_assessment: dict[str, Any] | None
    assumption_analysis: dict[str, Any] | None
    judgment: dict[str, Any] | None
    recommendation: dict[str, Any] | None
    review_action: Literal["approve", "revise", "reject"] | None
    review_notes: str | None
    review_feedback: str | None
    recommendation_revision_count: int
    review_history: list[dict[str, Any]]
    prior_evaluation: dict[str, Any] | None
    reused_from_evaluation_id: str | None
    evaluation_id: str | None
    evaluation_saved: bool
    thread_id: str | None
    status: Literal[
        "pending",
        "needs_clarification",
        "ready",
        "no_prior_evaluation",
        "prior_evaluation_found",
        "ready_for_research",
        "evaluation_reused",
        "researching",
        "research_complete",
        "competitor_research_complete",
        "market_feasibility_complete",
        "evidence_sufficient",
        "insufficient_evidence",
        "assumption_analysis_complete",
        "judgment_complete",
        "recommendation_complete",
        "revision_requested",
        "review_complete",
        "error",
    ]
    error_code: str | None
    error_message: str | None
