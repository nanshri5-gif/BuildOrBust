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
    research_sources: list[dict[str, str]]
    status: Literal[
        "pending",
        "needs_clarification",
        "ready",
        "researching",
        "research_complete",
        "error",
    ]
    error_code: str | None
    error_message: str | None

