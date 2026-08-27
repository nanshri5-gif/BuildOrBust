import json
import os
from typing import Literal, Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .state import BuildOrBustState


class DecisionCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion: str
    status: Literal["supported", "unsupported", "unknown"]
    evidence: str


class Judgment(BaseModel):
    """A decision grounded only in evidence already saved in graph state."""

    model_config = ConfigDict(extra="forbid")
    decision: Literal["BUILD", "VALIDATE", "PIVOT", "BUST"]
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    decisive_evidence: list[str] = Field(min_length=1, max_length=5)
    blocking_uncertainties: list[str] = Field(default_factory=list, max_length=5)
    decision_criteria: list[DecisionCriterion] = Field(min_length=3, max_length=6)


class JudgeFailure(Exception):
    def __init__(self, message: str, code: str = "judge_failure"):
        super().__init__(message)
        self.code = code


class Judge(Protocol):
    def decide(self, state: BuildOrBustState) -> Judgment: ...


class NebiusJudge:
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

    def decide(self, state: BuildOrBustState) -> Judgment:
        if self.client is None or not self.model:
            raise JudgeFailure(
                "Set NEBIUS_API_KEY and NEBIUS_MODEL before judgment.",
                "nebius_configuration_failure",
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
            "consumer_research": state.get("consumer_research"),
            "competitor_research": state.get("competitor_research"),
            "market_feasibility_research": state.get("market_feasibility_research"),
            "assumption_analysis": state.get("assumption_analysis"),
        }
        prompt = (
            "Act as the final evidence Judge. Use only the supplied reports; do not browse, "
            "introduce outside facts, or reinterpret missing evidence as negative evidence. "
            "Choose exactly one decision. BUILD requires strong evidence for the problem, "
            "differentiation, adoption, and feasibility with no unresolved fatal risk. "
            "VALIDATE means the opportunity is plausible but one or more high-impact claims "
            "remain unknown. PIVOT means evidence supports a related problem or opportunity "
            "but contradicts the current customer, solution, positioning, or business model. "
            "BUST requires evidence that a core assumption is false or a fatal constraint "
            "makes the idea untenable in its current form; missing evidence alone is never "
            "enough for BUST. Calibrate confidence to evidence quality and completeness. "
            "Every decision criterion must name the saved evidence or explicitly say it is "
            "unknown. Do not create a product roadmap or perform new research.\n\n"
            f"EVIDENCE:\n{json.dumps(evidence, ensure_ascii=False)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return only judgment JSON matching the supplied schema.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "build_or_bust_judgment",
                        "strict": True,
                        "schema": Judgment.model_json_schema(),
                    },
                },
            )
            message = response.choices[0].message
            if getattr(message, "refusal", None):
                raise JudgeFailure("Nebius refused to judge the evidence.", "model_refusal")
            if not message.content:
                raise JudgeFailure("Nebius returned no judgment.", "malformed_output")
            return Judgment.model_validate(json.loads(message.content))
        except JudgeFailure:
            raise
        except (IndexError, AttributeError, json.JSONDecodeError) as exc:
            raise JudgeFailure(f"Malformed judgment: {exc}", "malformed_output") from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise JudgeFailure(f"Malformed judgment: {exc}", "malformed_output") from exc
        except openai.APIError as exc:
            status = getattr(exc, "status_code", None)
            body = getattr(exc, "body", None)
            detail = body.get("detail") if isinstance(body, dict) else None
            context = f" (HTTP {status})" if status else ""
            if isinstance(detail, str) and detail:
                context += f": {detail}"
            raise JudgeFailure(
                f"The Nebius judgment request failed{context}.", "nebius_api_failure"
            ) from exc
