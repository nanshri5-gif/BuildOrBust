from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from .state import BuildOrBustState


class EvidenceAssessment(BaseModel):
    """Deterministic decision about whether research can support reasoning."""

    model_config = ConfigDict(extra="forbid")
    sufficient: bool
    source_counts: dict[str, int]
    independent_domain_counts: dict[str, int]
    extracted_page_counts: dict[str, int]
    coverage: dict[str, bool]
    failed_checks: list[str]


@dataclass(frozen=True)
class EvidenceThresholds:
    consumer_sources: int = 3
    consumer_domains: int = 2
    competitor_sources: int = 2
    competitor_domains: int = 2
    competitor_extracted_pages: int = 1
    market_sources: int = 3
    market_domains: int = 2


def _valid_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = []
    seen_urls: set[str] = set()
    for source in sources:
        url = str(source.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc and url not in seen_urls:
            seen_urls.add(url)
            valid.append(source)
    return valid


def _domain_count(sources: list[dict[str, Any]]) -> int:
    domains = {
        urlparse(str(source["url"])).netloc.lower().removeprefix("www.")
        for source in sources
    }
    return len(domains)


class EvidenceGate:
    """Stops unsupported ideas before generative analysis or judgment."""

    def __init__(self, thresholds: EvidenceThresholds | None = None):
        self.thresholds = thresholds or EvidenceThresholds()

    def assess(self, state: BuildOrBustState) -> EvidenceAssessment:
        groups = {
            "consumer": _valid_sources(state.get("research_sources", [])),
            "competitor": _valid_sources(state.get("competitor_sources", [])),
            "market": _valid_sources(state.get("market_feasibility_sources", [])),
        }
        source_counts = {name: len(sources) for name, sources in groups.items()}
        domain_counts = {name: _domain_count(sources) for name, sources in groups.items()}
        extracted_page_counts = {
            "competitor": sum(
                bool(source.get("content_extracted"))
                for source in groups["competitor"]
            )
        }

        consumer = state.get("consumer_research") or {}
        competitor = state.get("competitor_research") or {}
        market = state.get("market_feasibility_research") or {}
        coverage = {
            "consumer_pain_points": bool(consumer.get("pain_points")),
            "consumer_current_behaviors": bool(consumer.get("current_behaviors")),
            # An empty direct-competitor list is a valid researched outcome. The
            # report's presence proves the competitor node completed successfully.
            "competitor_search_completed": state.get("competitor_research") is not None,
            "existing_alternatives": bool(competitor.get("alternatives")),
            "market_demand_signals": bool(market.get("demand_signals")),
            "market_proxies": bool(market.get("market_proxies")),
            "adoption_constraints": bool(market.get("adoption_constraints")),
            "technical_dependencies": bool(market.get("technical_dependencies")),
            "feasibility_risks": bool(market.get("feasibility_risks")),
        }

        checks = {
            f"consumer needs at least {self.thresholds.consumer_sources} valid unique sources": source_counts["consumer"] >= self.thresholds.consumer_sources,
            f"consumer needs at least {self.thresholds.consumer_domains} independent domains": domain_counts["consumer"] >= self.thresholds.consumer_domains,
            f"competitor needs at least {self.thresholds.competitor_sources} valid unique sources": source_counts["competitor"] >= self.thresholds.competitor_sources,
            f"competitor needs at least {self.thresholds.competitor_domains} independent domains": domain_counts["competitor"] >= self.thresholds.competitor_domains,
            f"competitor needs at least {self.thresholds.competitor_extracted_pages} successfully extracted page": extracted_page_counts["competitor"] >= self.thresholds.competitor_extracted_pages,
            f"market needs at least {self.thresholds.market_sources} valid unique sources": source_counts["market"] >= self.thresholds.market_sources,
            f"market needs at least {self.thresholds.market_domains} independent domains": domain_counts["market"] >= self.thresholds.market_domains,
        }
        checks.update({f"required coverage missing: {name.replace('_', ' ')}": present for name, present in coverage.items()})
        failed = [description for description, passed in checks.items() if not passed]
        return EvidenceAssessment(
            sufficient=not failed,
            source_counts=source_counts,
            independent_domain_counts=domain_counts,
            extracted_page_counts=extracted_page_counts,
            coverage=coverage,
            failed_checks=failed,
        )
