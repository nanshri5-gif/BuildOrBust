from typing import Any

from .evidence_gate import EvidenceThresholds


def confidence_chart_data(state: dict[str, Any]) -> list[dict[str, float | str]]:
    """Return transparent 0–100 scores for the UI chart."""

    assessment = state.get("evidence_assessment") or {}
    sources = assessment.get("source_counts") or {}
    domains = assessment.get("independent_domain_counts") or {}
    extracted = assessment.get("extracted_page_counts") or {}
    coverage = assessment.get("coverage") or {}
    thresholds = EvidenceThresholds()

    def ratio(actual: int, required: int) -> float:
        return min(actual / required, 1.0) if required else 1.0

    consumer_coverage = sum(
        bool(coverage.get(key))
        for key in ("consumer_pain_points", "consumer_current_behaviors")
    ) / 2
    competitor_coverage = sum(
        bool(coverage.get(key))
        for key in ("direct_competitors", "existing_alternatives")
    ) / 2
    market_keys = (
        "market_demand_signals",
        "market_proxies",
        "adoption_constraints",
        "technical_dependencies",
        "feasibility_risks",
    )
    market_coverage = sum(bool(coverage.get(key)) for key in market_keys) / len(
        market_keys
    )
    scores = {
        "Consumer evidence readiness": min(
            ratio(sources.get("consumer", 0), thresholds.consumer_sources),
            ratio(domains.get("consumer", 0), thresholds.consumer_domains),
            consumer_coverage,
        ),
        "Competitor evidence readiness": min(
            ratio(sources.get("competitor", 0), thresholds.competitor_sources),
            ratio(domains.get("competitor", 0), thresholds.competitor_domains),
            ratio(
                extracted.get("competitor", 0),
                thresholds.competitor_extracted_pages,
            ),
            competitor_coverage,
        ),
        "Market evidence readiness": min(
            ratio(sources.get("market", 0), thresholds.market_sources),
            ratio(domains.get("market", 0), thresholds.market_domains),
            market_coverage,
        ),
    }
    judgment = state.get("judgment") or {}
    if isinstance(judgment.get("confidence"), (int, float)):
        scores["Judge confidence"] = min(max(judgment["confidence"], 0), 1)
    return [
        {"Measure": label, "Percent": round(score * 100, 1)}
        for label, score in scores.items()
    ]
