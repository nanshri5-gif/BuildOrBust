import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
import uuid

from pydantic import BaseModel, ConfigDict

from .state import BuildOrBustState, REQUIRED_FIELDS


REUSABLE_FIELDS = (
    "consumer_research",
    "research_sources",
    "competitor_research",
    "competitor_sources",
    "market_feasibility_research",
    "market_feasibility_sources",
    "evidence_assessment",
    "assumption_analysis",
    "judgment",
    "recommendation",
    "review_action",
    "review_notes",
    "recommendation_revision_count",
    "review_history",
)
PIPELINE_VERSION = "stage-9-v1"


class PriorEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    original_thread_id: str | None
    created_at: str
    expires_at: str
    decision: str
    review_action: str
    snapshot: dict[str, Any]


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    created_at: str
    decision: str
    review_action: str
    intake: dict[str, Any]
    snapshot: dict[str, Any]


class IdeaRegistryFailure(Exception):
    pass


class IdeaRegistry(Protocol):
    def find_recent(self, state: BuildOrBustState) -> PriorEvaluation | None: ...

    def save(self, state: BuildOrBustState) -> str: ...


def idea_fingerprint(state: BuildOrBustState) -> str:
    def normalize(value: Any) -> str:
        return " ".join(re.sub(r"[^\w]+", " ", str(value or "").casefold()).split())

    normalized = {
        field: normalize(state.get(field))
        for field in REQUIRED_FIELDS
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class SQLiteIdeaRegistry:
    """Application-owned evaluation registry beside LangGraph checkpoint tables."""

    def __init__(self, db_path: str | Path, freshness_days: int = 90):
        self.db_path = str(db_path)
        self.freshness_days = freshness_days
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _setup(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS idea_evaluations (
                        evaluation_id TEXT PRIMARY KEY,
                        fingerprint TEXT NOT NULL,
                        original_thread_id TEXT,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        confidence REAL,
                        review_action TEXT NOT NULL,
                        intake_json TEXT NOT NULL,
                        model_id TEXT,
                        pipeline_version TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_idea_evaluations_fingerprint
                        ON idea_evaluations(fingerprint, expires_at);
                    CREATE TABLE IF NOT EXISTS evaluation_sources (
                        evaluation_id TEXT NOT NULL,
                        research_type TEXT NOT NULL,
                        title TEXT,
                        url TEXT NOT NULL,
                        FOREIGN KEY (evaluation_id) REFERENCES idea_evaluations(evaluation_id)
                    );
                    CREATE TABLE IF NOT EXISTS evaluation_reviews (
                        evaluation_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        notes TEXT,
                        revision_count INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (evaluation_id) REFERENCES idea_evaluations(evaluation_id)
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise IdeaRegistryFailure(f"Could not initialize the idea registry: {exc}") from exc

    def find_recent(self, state: BuildOrBustState) -> PriorEvaluation | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT evaluation_id, original_thread_id, created_at, expires_at,
                           decision, review_action, snapshot_json
                    FROM idea_evaluations
                    WHERE fingerprint = ? AND expires_at > ?
                      AND review_action IN ('approve', 'reject')
                      AND pipeline_version = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (
                        idea_fingerprint(state),
                        datetime.now(UTC).isoformat(),
                        PIPELINE_VERSION,
                    ),
                ).fetchone()
        except sqlite3.Error as exc:
            raise IdeaRegistryFailure(f"Could not query the idea registry: {exc}") from exc
        if row is None:
            return None
        try:
            snapshot = json.loads(row["snapshot_json"])
            return PriorEvaluation(
                evaluation_id=row["evaluation_id"],
                original_thread_id=row["original_thread_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                decision=row["decision"],
                review_action=row["review_action"],
                snapshot=snapshot,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise IdeaRegistryFailure(f"Stored evaluation is malformed: {exc}") from exc

    def list_recent(self, limit: int = 20) -> list[EvaluationSummary]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT evaluation_id, created_at, decision, review_action,
                           intake_json, snapshot_json
                    FROM idea_evaluations
                    WHERE review_action IN ('approve', 'reject')
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(limit, 100)),),
                ).fetchall()
            return [
                EvaluationSummary(
                    evaluation_id=row["evaluation_id"],
                    created_at=row["created_at"],
                    decision=row["decision"],
                    review_action=row["review_action"],
                    intake=json.loads(row["intake_json"]),
                    snapshot=json.loads(row["snapshot_json"]),
                )
                for row in rows
            ]
        except (sqlite3.Error, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise IdeaRegistryFailure(f"Could not load evaluation history: {exc}") from exc

    def save(self, state: BuildOrBustState) -> str:
        review_action = state.get("review_action")
        judgment = state.get("judgment") or {}
        if review_action not in {"approve", "reject"} or not judgment.get("decision"):
            raise IdeaRegistryFailure("Only approved or rejected completed evaluations can be saved.")
        evaluation_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(days=self.freshness_days)
        snapshot = {field: state.get(field) for field in REUSABLE_FIELDS}
        intake = {field: state.get(field) for field in REQUIRED_FIELDS}
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO idea_evaluations (
                        evaluation_id, fingerprint, original_thread_id, created_at,
                        expires_at, decision, confidence, review_action, snapshot_json
                        , intake_json, model_id, pipeline_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evaluation_id,
                        idea_fingerprint(state),
                        state.get("thread_id"),
                        created_at.isoformat(),
                        expires_at.isoformat(),
                        judgment["decision"],
                        judgment.get("confidence"),
                        review_action,
                        json.dumps(snapshot, ensure_ascii=False),
                        json.dumps(intake, ensure_ascii=False),
                        os.getenv("NEBIUS_MODEL"),
                        PIPELINE_VERSION,
                    ),
                )
                source_groups = {
                    "consumer": state.get("research_sources", []),
                    "competitor": state.get("competitor_sources", []),
                    "market": state.get("market_feasibility_sources", []),
                }
                for research_type, sources in source_groups.items():
                    connection.executemany(
                        """
                        INSERT INTO evaluation_sources
                            (evaluation_id, research_type, title, url)
                        VALUES (?, ?, ?, ?)
                        """,
                        [
                            (evaluation_id, research_type, source.get("title"), source["url"])
                            for source in sources
                            if source.get("url")
                        ],
                    )
                connection.executemany(
                    """
                    INSERT INTO evaluation_reviews
                        (evaluation_id, action, notes, revision_count, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            evaluation_id,
                            item.get("action", ""),
                            item.get("notes"),
                            int(item.get("revision_count", 0)),
                            str(item.get("reviewed_at") or created_at.isoformat()),
                        )
                        for item in state.get("review_history", [])
                    ],
                )
        except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            raise IdeaRegistryFailure(f"Could not save the evaluation: {exc}") from exc
        return evaluation_id
