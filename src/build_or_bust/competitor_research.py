import os
from typing import Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .consumer_research import _sources
from .state import BuildOrBustState


class Competitor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    offering: str
    pricing: str | None
    strengths: list[str] = Field(min_length=1, max_length=3)
    weaknesses: list[str] = Field(min_length=1, max_length=3)


class CompetitorResearch(BaseModel):
    """Evidence about direct competitors and existing alternatives."""

    model_config = ConfigDict(extra="forbid")
    summary: str
    direct_competitors: list[Competitor] = Field(min_length=1, max_length=5)
    alternatives: list[str] = Field(min_length=1, max_length=5)
    differentiation_gaps: list[str] = Field(default_factory=list, max_length=5)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=5)


class CompetitorResearchFailure(Exception):
    pass


class CompetitorResearcher(Protocol):
    def research(
        self, state: BuildOrBustState
    ) -> tuple[CompetitorResearch, list[dict[str, str]]]: ...


class OpenAICompetitorResearcher:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        self.client = client or OpenAI(max_retries=2, timeout=60.0)
        self.model = model or os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5.6-luna")

    def research(
        self, state: BuildOrBustState
    ) -> tuple[CompetitorResearch, list[dict[str, str]]]:
        consumer_summary = (state.get("consumer_research") or {}).get("summary", "Not available")
        prompt = (
            "Research competitors only for this product concept in the stated geography. "
            "Use current first-party product and pricing pages where possible. Separate "
            "direct competitors from non-product alternatives. Report pricing as unknown "
            "when it cannot be verified. Do not estimate market size, assess technical "
            "feasibility, or make a build decision. Do not put URLs or citation markup "
            "inside the structured fields; sources are captured separately.\n\n"
            f"Product idea: {state['product_idea']}\n"
            f"Target customer: {state['target_customer']}\n"
            f"Geography: {state['geography']}\n"
            f"Problem: {state['problem']}\n"
            f"Product type: {state['product_type']}\n"
            f"Consumer research summary: {consumer_summary}"
        )
        try:
            response = self.client.responses.parse(
                model=self.model,
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                input=prompt,
                text_format=CompetitorResearch,
            )
            if response.output_parsed is None:
                raise CompetitorResearchFailure(
                    "OpenAI returned no parseable competitor research."
                )
            sources = _sources(response)
            if not sources:
                raise CompetitorResearchFailure(
                    "Competitor research returned without source URLs."
                )
            return response.output_parsed, sources
        except CompetitorResearchFailure:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise CompetitorResearchFailure(
                f"Malformed competitor research: {exc}"
            ) from exc
        except openai.APIError as exc:
            raise CompetitorResearchFailure(
                "The OpenAI competitor research request failed."
            ) from exc
