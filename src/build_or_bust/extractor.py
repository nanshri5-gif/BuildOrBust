import json
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


class NebiusExtractor:
    def __init__(self, client: OpenAI | None = None, model: str | None = None):
        api_key = os.getenv("NEBIUS_API_KEY")
        self.client = client or (
            OpenAI(
                api_key=api_key,
                base_url=os.getenv(
                    "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
                ),
                max_retries=2,
                timeout=30.0,
            )
            if api_key
            else None
        )
        self.model = model or os.getenv("NEBIUS_MODEL")

    def extract(self, user_text: str) -> IntakeData:
        if self.client is None or not self.model:
            raise ExtractionFailure(
                "nebius_configuration_failure",
                "Set NEBIUS_API_KEY and NEBIUS_MODEL in .env before running intake.",
            )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract only facts stated or clearly implied by the user. "
                            "Use null for anything unknown. Keep values concise and "
                            "return only JSON matching the supplied schema."
                        ),
                    },
                    {"role": "user", "content": user_text},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "intake_data",
                        "strict": True,
                        "schema": IntakeData.model_json_schema(),
                    },
                },
            )
            message = response.choices[0].message
            if getattr(message, "refusal", None):
                raise ExtractionFailure(
                    "model_refusal", "Nebius refused to process the intake request."
                )
            if not message.content:
                raise ExtractionFailure(
                    "malformed_output", "Nebius returned no structured intake data."
                )
            return IntakeData.model_validate(json.loads(message.content))
        except ExtractionFailure:
            raise
        except (IndexError, AttributeError, json.JSONDecodeError) as exc:
            raise ExtractionFailure("malformed_output", str(exc)) from exc
        except ValidationError as exc:
            raise ExtractionFailure("malformed_output", str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise ExtractionFailure("malformed_output", str(exc)) from exc
        except openai.APIError as exc:
            status = getattr(exc, "status_code", None)
            body = getattr(exc, "body", None)
            detail = body.get("detail") if isinstance(body, dict) else None
            context = f" (HTTP {status})" if status else ""
            if isinstance(detail, str) and detail:
                context += f": {detail}"
            raise ExtractionFailure(
                "nebius_api_failure",
                f"The Nebius request failed{context}. Retry this same thread later.",
            ) from exc
