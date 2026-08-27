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
    def __init__(self, message: str, code: str = "assumption_killer_failure"):
        super().__init__(message)
        self.code = code


class AssumptionKiller(Protocol):
    def analyze(self, state: BuildOrBustState) -> AssumptionAnalysis: ...


class NebiusAssumptionKiller:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        api_key = os.getenv("NEBIUS_API_KEY")
        self.client = client or (
            OpenAI(
                api_key=api_key,
                base_url=os.getenv(
                    "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
                ),
                max_retries=2,
                timeout=60.0,
            )
            if api_key
            else None
        )
        self.model = model or os.getenv("NEBIUS_MODEL")

    def analyze(self, state: BuildOrBustState) -> AssumptionAnalysis:
        if self.client is None or not self.model:
            raise AssumptionKillerFailure(
                "Set NEBIUS_API_KEY and NEBIUS_MODEL before assumption analysis.",
                "nebius_configuration_failure",
            )
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return only assumption analysis JSON matching the schema.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "assumption_analysis",
                        "strict": True,
                        "schema": AssumptionAnalysis.model_json_schema(),
                    },
                },
            )
            message = response.choices[0].message
            if getattr(message, "refusal", None):
                raise AssumptionKillerFailure(
                    "Nebius refused to perform assumption analysis.", "model_refusal"
                )
            if not message.content:
                raise AssumptionKillerFailure(
                    "Nebius returned no assumption analysis.", "malformed_output"
                )
            return AssumptionAnalysis.model_validate(json.loads(message.content))
        except AssumptionKillerFailure:
            raise
        except (IndexError, AttributeError, json.JSONDecodeError) as exc:
            raise AssumptionKillerFailure(
                f"Malformed assumption analysis: {exc}", "malformed_output"
            ) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise AssumptionKillerFailure(
                f"Malformed assumption analysis: {exc}", "malformed_output"
            ) from exc
        except openai.APIError as exc:
            status = getattr(exc, "status_code", None)
            body = getattr(exc, "body", None)
            detail = body.get("detail") if isinstance(body, dict) else None
            context = f" (HTTP {status})" if status else ""
            if isinstance(detail, str) and detail:
                context += f": {detail}"
            raise AssumptionKillerFailure(
                f"The Nebius assumption analysis request failed{context}.",
                "nebius_api_failure",
            ) from exc
