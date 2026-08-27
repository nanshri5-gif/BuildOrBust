import os
from typing import Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .state import BuildOrBustState


class ConsumerResearch(BaseModel):
    """Evidence about the target consumer; no market or competitor analysis."""

    model_config = ConfigDict(extra="forbid")
    summary: str
    pain_points: list[str] = Field(min_length=1, max_length=5)
    current_behaviors: list[str] = Field(min_length=1, max_length=5)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=5)


class ResearchFailure(Exception):
    pass


class Researcher(Protocol):
    def research(self, state: BuildOrBustState) -> tuple[ConsumerResearch, list[dict[str, str]]]: ...


def _sources(response: object) -> list[dict[str, str]]:
    """Collect and deduplicate sources returned by the hosted web-search tool."""

    payload = response.model_dump()  # type: ignore[attr-defined]
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload.get("output", []):
        action = item.get("action") or {}
        for source in action.get("sources") or []:
            url = source.get("url")
            if url and url not in seen:
                found.append({"title": source.get("title") or url, "url": url})
                seen.add(url)
    return found


class OpenAIConsumerResearcher:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        self.client = client or OpenAI(max_retries=2, timeout=60.0)
        self.model = model or os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5.6-luna")

    def research(self, state: BuildOrBustState) -> tuple[ConsumerResearch, list[dict[str, str]]]:
        prompt = (
            "Research consumers only for this product concept. Find recent, credible "
            "evidence about their pain points and current behaviors. Do not analyze "
            "competitors, market size, technical feasibility, or make a build decision. "
            "State uncertainty in evidence_gaps.\n\n"
            f"Product idea: {state['product_idea']}\n"
            f"Target customer: {state['target_customer']}\n"
            f"Geography: {state['geography']}\n"
            f"Problem: {state['problem']}\n"
            f"Product type: {state['product_type']}"
        )
        try:
            response = self.client.responses.parse(
                model=self.model,
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                input=prompt,
                text_format=ConsumerResearch,
            )
            if response.output_parsed is None:
                raise ResearchFailure("OpenAI returned no parseable consumer research.")
            sources = _sources(response)
            if not sources:
                raise ResearchFailure("Consumer research returned without source URLs.")
            return response.output_parsed, sources
        except ResearchFailure:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise ResearchFailure(f"Malformed consumer research: {exc}") from exc
        except openai.APIError as exc:
            raise ResearchFailure("The OpenAI consumer research request failed.") from exc
