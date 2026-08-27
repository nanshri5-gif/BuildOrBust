import argparse
import os
import uuid

from dotenv import load_dotenv
from langgraph.types import Command

from .graph import open_graph


def _show_sources(sources: list[dict[str, str]], limit: int = 10) -> None:
    for source in sources[:limit]:
        print(f"    - {source['title']}: {source['url']}")
    remaining = len(sources) - limit
    if remaining > 0:
        print(f"    ... {remaining} more sources saved in the checkpoint")


def _show(result: dict) -> None:
    if result.get("__interrupt__"):
        print(result["__interrupt__"][0].value["question"])
    elif result.get("status") == "error":
        print(f"Error [{result.get('error_code')}]: {result.get('error_message')}")
    else:
        print("Intake complete:")
        fields = ("product_idea", "target_customer", "geography", "problem", "product_type")
        for field in fields:
            print(f"  {field.replace('_', ' ').title()}: {result.get(field)}")
        report = result.get("consumer_research")
        if report:
            print("\nConsumer research:")
            print(f"  Summary: {report['summary']}")
            print("  Pain points:")
            for item in report["pain_points"]:
                print(f"    - {item}")
            print("  Current behaviors:")
            for item in report["current_behaviors"]:
                print(f"    - {item}")
            if report["evidence_gaps"]:
                print("  Evidence gaps:")
                for item in report["evidence_gaps"]:
                    print(f"    - {item}")
            print("  Sources:")
            _show_sources(result.get("research_sources", []))
        competitors = result.get("competitor_research")
        if competitors:
            print("\nCompetitor research:")
            print(f"  Summary: {competitors['summary']}")
            print("  Direct competitors:")
            for competitor in competitors["direct_competitors"]:
                print(f"    - {competitor['name']}: {competitor['offering']}")
                print(f"      Pricing: {competitor['pricing'] or 'Unknown'}")
                print(f"      Strengths: {', '.join(competitor['strengths'])}")
                print(f"      Weaknesses: {', '.join(competitor['weaknesses'])}")
            print("  Alternatives:")
            for item in competitors["alternatives"]:
                print(f"    - {item}")
            if competitors["differentiation_gaps"]:
                print("  Differentiation gaps:")
                for item in competitors["differentiation_gaps"]:
                    print(f"    - {item}")
            if competitors["evidence_gaps"]:
                print("  Evidence gaps:")
                for item in competitors["evidence_gaps"]:
                    print(f"    - {item}")
            print("  Sources:")
            _show_sources(result.get("competitor_sources", []))
        market = result.get("market_feasibility_research")
        if market:
            print("\nMarket and feasibility research:")
            print(f"  Summary: {market['summary']}")
            sections = (
                ("Demand signals", "demand_signals"),
                ("Market proxies", "market_proxies"),
                ("Adoption constraints", "adoption_constraints"),
                ("Technical dependencies", "technical_dependencies"),
                ("Feasibility risks", "feasibility_risks"),
                ("Evidence gaps", "evidence_gaps"),
            )
            for label, key in sections:
                if market[key]:
                    print(f"  {label}:")
                    for item in market[key]:
                        print(f"    - {item}")
            print("  Sources:")
            _show_sources(result.get("market_feasibility_sources", []))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Build or Bust — Stages 1–4")
    parser.add_argument("idea", nargs="?", help="Product idea to normalize")
    parser.add_argument("--thread", default=str(uuid.uuid4()), help="Persistent run ID")
    parser.add_argument("--resume", help="Answer a saved clarification question")
    parser.add_argument(
        "--show", action="store_true", help="Display saved state without running the graph"
    )
    args = parser.parse_args()

    config = {"configurable": {"thread_id": args.thread}}
    with open_graph(os.getenv("CHECKPOINT_DB", "build_or_bust.db")) as graph:
        if args.show:
            result = dict(graph.get_state(config).values)
            if not result:
                result = {
                    "status": "error",
                    "error_code": "checkpoint_not_found",
                    "error_message": "No saved checkpoint exists for this thread ID.",
                }
        else:
            request = Command(resume=args.resume) if args.resume is not None else {
                "raw_input": args.idea or "", "status": "pending"
            }
            result = graph.invoke(request, config=config)
        print(f"Thread: {args.thread}")
        _show(result)


if __name__ == "__main__":
    main()
