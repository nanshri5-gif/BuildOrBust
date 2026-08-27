import os
from typing import Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .consumer_research import _sources
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
    evidence_gaps: list[str] = Field(default_factory=list, max_length=5)


class MarketFeasibilityFailure(Exception):
    pass


class MarketFeasibilityResearcher(Protocol):
    def research(
        self, state: BuildOrBustState
    ) -> tuple[MarketFeasibilityResearch, list[dict[str, str]]]: ...


class OpenAIMarketFeasibilityResearcher:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        self.client = client or OpenAI(max_retries=2, timeout=60.0)
        self.model = model or os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5.6-luna")

    def research(
        self, state: BuildOrBustState
    ) -> tuple[MarketFeasibilityResearch, list[dict[str, str]]]:
        consumer = state.get("consumer_research") or {}
        competitors = state.get("competitor_research") or {}
        competitor_names = [
            item.get("name", "Unknown")
            for item in competitors.get("direct_competitors", [])
        ]
        prompt = (
            "Research market signals and implementation feasibility for this product. "
            "Use current authoritative sources and clearly label indirect market proxies. "
            "Never invent TAM, revenue, user counts, growth rates, or technical capabilities. "
            "For technical feasibility, identify concrete data, platform, integration, privacy, "
            "and operational dependencies plus risks. Do not make a BUILD/PIVOT/BUST decision, "
            "kill assumptions, or recommend a product strategy. Do not put URLs or citation "
            "markup inside structured fields; sources are captured separately.\n\n"
            f"Product idea: {state['product_idea']}\n"
            f"Target customer: {state['target_customer']}\n"
            f"Geography: {state['geography']}\n"
            f"Problem: {state['problem']}\n"
            f"Product type: {state['product_type']}\n"
            f"Consumer summary: {consumer.get('summary', 'Not available')}\n"
            f"Known competitors: {', '.join(competitor_names) or 'Not available'}"
        )
        try:
            response = self.client.responses.parse(
                model=self.model,
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                input=prompt,
                text_format=MarketFeasibilityResearch,
            )
            if response.output_parsed is None:
                raise MarketFeasibilityFailure(
                    "OpenAI returned no parseable market and feasibility research."
                )
            sources = _sources(response)
            if not sources:
                raise MarketFeasibilityFailure(
                    "Market and feasibility research returned without source URLs."
                )
            return response.output_parsed, sources
        except MarketFeasibilityFailure:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise MarketFeasibilityFailure(
                f"Malformed market and feasibility research: {exc}"
            ) from exc
        except openai.APIError as exc:
            raise MarketFeasibilityFailure(
                "The OpenAI market and feasibility request failed."
            ) from exc
