import os
from typing import Protocol

import openai
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError


class IntakeData(BaseModel):
    """Nullable values let the graph identify facts the user did not supply."""

    model_config = ConfigDict(extra="forbid")
    product_idea: str | None
    target_customer: str | None
    geography: str | None
    problem: str | None
    product_type: str | None


class ExtractionFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Extractor(Protocol):
    def extract(self, user_text: str) -> IntakeData: ...


class OpenAIExtractor:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        self.client = client or OpenAI(max_retries=2, timeout=30.0)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def extract(self, user_text: str) -> IntakeData:
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "developer",
                        "content": (
                            "Extract only facts stated or clearly implied by the user. "
                            "Use null for anything unknown. Keep values concise."
                        ),
                    },
                    {"role": "user", "content": user_text},
                ],
                text_format=IntakeData,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ExtractionFailure(
                    "malformed_output", "OpenAI returned no parseable structured intake data."
                )
            return parsed
        except ExtractionFailure:
            raise
        except ValidationError as exc:
            raise ExtractionFailure("malformed_output", str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise ExtractionFailure("malformed_output", str(exc)) from exc
        except openai.APIError as exc:
            raise ExtractionFailure(
                "openai_api_failure",
                "The OpenAI request failed. Retry this same thread later.",
            ) from exc
