from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .consumer_research import ResearchFailure, YouMCPClient
from .state import BuildOrBustState


class MarketFeasibilityResearch(BaseModel):
    """Sourced market signals and implementation feasibility evidence."""

    model_config = ConfigDict(extra="forbid")
    summary: str
    demand_signals: list[str] = Field(min_length=1, max_length=5)
    market_proxies: list[str] = Field(min_length=1, max_length=5)
    adoption_constraints: list[str] = Field(min_length=1, max_length=5)
    technical_dependencies: list[str] = Field(min_length=1, max_length=5)
    feasibility_risks: list[str] = Field(min_length=1, max_length=5)
    evidence_gaps: list[str] = Field(max_length=5)


class MarketFeasibilityFailure(Exception):
    pass


class MarketFeasibilityResearcher(Protocol):
    def research(
        self, state: BuildOrBustState
    ) -> tuple[MarketFeasibilityResearch, list[dict[str, str]]]: ...


class MarketResearchClient(Protocol):
    def research(
        self, question: str, output_schema: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, str]]]: ...


class YouMCPMarketFeasibilityResearcher:
    def __init__(self, research_client: MarketResearchClient | None = None):
        self.research_client = research_client or YouMCPClient()

    def research(
        self, state: BuildOrBustState
    ) -> tuple[MarketFeasibilityResearch, list[dict[str, str]]]:
        consumer = state.get("consumer_research") or {}
        competitors = state.get("competitor_research") or {}
        competitor_names = [
            item.get("name", "Unknown")
            for item in competitors.get("direct_competitors", [])
        ]
        question = (
            "Research market signals and implementation feasibility for this product. "
            "Use current authoritative sources and clearly label indirect market proxies. "
            "Never invent TAM, revenue, user counts, growth rates, or technical capabilities. "
            "For technical feasibility, identify concrete data, platform, integration, privacy, "
            "and operational dependencies plus risks. Do not make a BUILD/PIVOT/BUST decision, "
            "kill assumptions, or recommend a product strategy.\n\n"
            f"Product idea: {state['product_idea']}\n"
            f"Target customer: {state['target_customer']}\n"
            f"Geography: {state['geography']}\n"
            f"Problem: {state['problem']}\n"
            f"Product type: {state['product_type']}\n"
            f"Consumer summary: {consumer.get('summary', 'Not available')}\n"
            f"Known competitors: {', '.join(competitor_names) or 'Not available'}"
        )
        try:
            content, sources = self.research_client.research(
                question, MarketFeasibilityResearch.model_json_schema()
            )
            for key in (
                "demand_signals",
                "market_proxies",
                "adoption_constraints",
                "technical_dependencies",
                "feasibility_risks",
                "evidence_gaps",
            ):
                if isinstance(content.get(key), list):
                    content[key] = content[key][:5]
            report = MarketFeasibilityResearch.model_validate(content)
            return report, sources
        except MarketFeasibilityFailure:
            raise
        except ResearchFailure as exc:
            raise MarketFeasibilityFailure(
                f"You.com MCP market and feasibility research failed: {exc}"
            ) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise MarketFeasibilityFailure(
                f"Malformed market and feasibility research: {exc}"
            ) from exc
