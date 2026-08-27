import json
import os
from typing import Literal, Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .state import BuildOrBustState


class CriticalAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str
    category: Literal["consumer", "competitive", "market", "technical", "business"]
    evidence_for: list[str] = Field(default_factory=list, max_length=4)
    evidence_against: list[str] = Field(default_factory=list, max_length=4)
    evidence_strength: Literal["weak", "mixed", "strong"]
    impact_if_false: Literal["low", "medium", "high", "fatal"]
    validation_experiment: str
    success_criterion: str


class AssumptionAnalysis(BaseModel):
    """A skeptical analysis grounded only in previously collected evidence."""

    model_config = ConfigDict(extra="forbid")
    summary: str
    critical_assumptions: list[CriticalAssumption] = Field(min_length=3, max_length=8)
    contradictions: list[str] = Field(default_factory=list, max_length=5)
    fatal_risks: list[str] = Field(default_factory=list, max_length=5)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=5)


class AssumptionKillerFailure(Exception):
    pass


class AssumptionKiller(Protocol):
    def analyze(self, state: BuildOrBustState) -> AssumptionAnalysis: ...


class OpenAIAssumptionKiller:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        self.client = client or OpenAI(max_retries=2, timeout=60.0)
        self.model = model or os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-5.6-luna")

    def analyze(self, state: BuildOrBustState) -> AssumptionAnalysis:
        evidence = {
            "intake": {
                "product_idea": state.get("product_idea"),
                "target_customer": state.get("target_customer"),
                "geography": state.get("geography"),
                "problem": state.get("problem"),
                "product_type": state.get("product_type"),
            },
            "consumer_research": state.get("consumer_research"),
            "competitor_research": state.get("competitor_research"),
            "market_feasibility_research": state.get("market_feasibility_research"),
        }
        prompt = (
            "Act as a skeptical Assumption Killer. Analyze only the evidence supplied "
            "below; do not browse, add outside facts, or treat missing evidence as proof. "
            "Identify the assumptions that must be true for this product to succeed. Rank "
            "the most consequential assumptions first. Cite evidence by naming its report "
            "and paraphrasing the relevant finding. Separate evidence for and against. "
            "Make each validation experiment low-cost, specific, and measurable. A fatal "
            "risk means the idea would not work in its current form if the assumption is "
            "false. Do not issue a BUILD, VALIDATE, PIVOT, or BUST verdict.\n\n"
            f"EVIDENCE:\n{json.dumps(evidence, ensure_ascii=False)}"
        )
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=prompt,
                text_format=AssumptionAnalysis,
            )
            if response.output_parsed is None:
                raise AssumptionKillerFailure(
                    "OpenAI returned no parseable assumption analysis."
                )
            return response.output_parsed
        except AssumptionKillerFailure:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise AssumptionKillerFailure(
                f"Malformed assumption analysis: {exc}"
            ) from exc
        except openai.APIError as exc:
            raise AssumptionKillerFailure(
                "The OpenAI assumption analysis request failed."
            ) from exc
