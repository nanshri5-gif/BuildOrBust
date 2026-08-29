import json
import os
from typing import Literal, Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .state import BuildOrBustState


class RecommendedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    purpose: str
    completion_criterion: str


class ValidationExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis: str
    method: str
    success_criterion: str
    failure_signal: str


class Recommendation(BaseModel):
    """An action plan constrained by the Judge's saved decision."""

    model_config = ConfigDict(extra="forbid")
    decision: Literal["BUILD", "VALIDATE", "PIVOT", "BUST"]
    recommended_direction: str
    next_actions: list[RecommendedAction] = Field(min_length=1, max_length=5)
    validation_experiments: list[ValidationExperiment] = Field(max_length=5)
    build_now: list[str] = Field(max_length=5)
    do_not_build_yet: list[str] = Field(max_length=5)
    evidence_used: list[str] = Field(min_length=1, max_length=5)
    unresolved_questions: list[str] = Field(max_length=5)
    human_review_questions: list[str] = Field(min_length=1, max_length=5)


class RecommendationFailure(Exception):
    def __init__(self, message: str, code: str = "recommendation_failure"):
        super().__init__(message)
        self.code = code


class RecommendationAgent(Protocol):
    def recommend(self, state: BuildOrBustState) -> Recommendation: ...


class NebiusRecommendationAgent:
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

    def recommend(self, state: BuildOrBustState) -> Recommendation:
        if self.client is None or not self.model:
            raise RecommendationFailure(
                "Set NEBIUS_API_KEY and NEBIUS_MODEL before recommendation.",
                "nebius_configuration_failure",
            )
        judgment = state.get("judgment") or {}
        judged_decision = judgment.get("decision")
        if judged_decision not in {"BUILD", "VALIDATE", "PIVOT", "BUST"}:
            raise RecommendationFailure(
                "A valid saved judgment is required before recommendation.",
                "missing_judgment",
            )
        evidence = {
            "intake": {
                key: state.get(key)
                for key in (
                    "product_idea",
                    "target_customer",
                    "geography",
                    "problem",
                    "product_type",
                )
            },
            "evidence_assessment": state.get("evidence_assessment"),
            "consumer_research": state.get("consumer_research"),
            "competitor_research": state.get("competitor_research"),
            "market_feasibility_research": state.get("market_feasibility_research"),
            "assumption_analysis": state.get("assumption_analysis"),
            "judgment": judgment,
            "current_recommendation": state.get("recommendation"),
            "revision_feedback": state.get("review_feedback"),
        }
        prompt = (
            "Create an actionable recommendation using only the saved evidence. Do not "
            "browse or add outside facts. Copy the Judge's decision exactly and never "
            "upgrade or soften it. For VALIDATE, prioritize cheap experiments over product "
            "development. For BUILD, limit build_now to the smallest evidence-supported "
            "scope. For PIVOT, describe tests for the supported direction without assuming "
            "it succeeds. For BUST, recommend stopping the current idea; build_now must be "
            "empty. Every experiment needs a measurable success criterion and failure "
            "signal. evidence_used must name and paraphrase saved evidence. Keep unresolved "
            "claims explicit and end with questions requiring human review. If revision "
            "feedback is present, revise the action plan in response while preserving the "
            "Judge's decision and all other constraints.\n\n"
            f"SAVED STATE:\n{json.dumps(evidence, ensure_ascii=False)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return only recommendation JSON matching the schema.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "build_or_bust_recommendation",
                        "strict": True,
                        "schema": Recommendation.model_json_schema(),
                    },
                },
            )
            message = response.choices[0].message
            if getattr(message, "refusal", None):
                raise RecommendationFailure(
                    "Nebius refused to create a recommendation.", "model_refusal"
                )
            if not message.content:
                raise RecommendationFailure(
                    "Nebius returned no recommendation.", "malformed_output"
                )
            result = Recommendation.model_validate(json.loads(message.content))
            if result.decision != judged_decision:
                raise RecommendationFailure(
                    "The recommendation changed the Judge's decision.",
                    "decision_mismatch",
                )
            if judged_decision == "BUST" and result.build_now:
                raise RecommendationFailure(
                    "A BUST recommendation cannot include build-now work.",
                    "decision_mismatch",
                )
            return result
        except RecommendationFailure:
            raise
        except (IndexError, AttributeError, json.JSONDecodeError) as exc:
            raise RecommendationFailure(
                f"Malformed recommendation: {exc}", "malformed_output"
            ) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise RecommendationFailure(
                f"Malformed recommendation: {exc}", "malformed_output"
            ) from exc
        except openai.APIError as exc:
            status = getattr(exc, "status_code", None)
            context = f" (HTTP {status})" if status else ""
            raise RecommendationFailure(
                f"The Nebius recommendation request failed{context}.",
                "nebius_api_failure",
            ) from exc
