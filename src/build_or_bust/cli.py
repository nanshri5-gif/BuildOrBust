import argparse
import os
import uuid

from dotenv import load_dotenv
from langgraph.types import Command

from .graph import open_graph


def _show_sources(sources: list[dict], limit: int = 10) -> None:
    for source in sources[:limit]:
        print(f"    - {source['title']}: {source['url']}")
    remaining = len(sources) - limit
    if remaining > 0:
        print(f"    ... {remaining} more sources saved in the checkpoint")


def _show(result: dict) -> None:
    prompt = result["__interrupt__"][0].value if result.get("__interrupt__") else None
    if prompt and not prompt.get("choices"):
        print(prompt["question"])
    elif result.get("status") == "error":
        print(f"Error [{result.get('error_code')}]: {result.get('error_message')}")
    elif result.get("status") == "insufficient_information":
        print(f"INSUFFICIENT_INFORMATION: {result.get('error_message')}")
    elif result.get("status") == "insufficient_evidence":
        assessment = result["evidence_assessment"]
        print("INSUFFICIENT_EVIDENCE: research did not meet the evidence gate.")
        print(f"  Valid sources: {assessment['source_counts']}")
        print(f"  Independent domains: {assessment['independent_domain_counts']}")
        print("  Failed checks:")
        for check in assessment["failed_checks"]:
            print(f"    - {check}")
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
        assessment = result.get("evidence_assessment")
        if assessment:
            print("\nEvidence gate: PASSED")
            print(f"  Valid sources: {assessment['source_counts']}")
            print(f"  Independent domains: {assessment['independent_domain_counts']}")
        assumptions = result.get("assumption_analysis")
        if assumptions:
            print("\nAssumption Killer:")
            print(f"  Summary: {assumptions['summary']}")
            print("  Critical assumptions:")
            for number, assumption in enumerate(
                assumptions["critical_assumptions"], start=1
            ):
                print(f"    {number}. {assumption['statement']}")
                print(f"       Category: {assumption['category']}")
                print(f"       Evidence strength: {assumption['evidence_strength']}")
                print(f"       Impact if false: {assumption['impact_if_false']}")
                if assumption["evidence_for"]:
                    print(f"       Evidence for: {'; '.join(assumption['evidence_for'])}")
                if assumption["evidence_against"]:
                    print(
                        f"       Evidence against: {'; '.join(assumption['evidence_against'])}"
                    )
                print(f"       Experiment: {assumption['validation_experiment']}")
                print(f"       Success criterion: {assumption['success_criterion']}")
            sections = (
                ("Contradictions", "contradictions"),
                ("Fatal risks", "fatal_risks"),
                ("Unresolved questions", "unresolved_questions"),
            )
            for label, key in sections:
                if assumptions[key]:
                    print(f"  {label}:")
                    for item in assumptions[key]:
                        print(f"    - {item}")
        judgment = result.get("judgment")
        if judgment:
            print("\nJudge:")
            print(f"  Decision: {judgment['decision']}")
            print(f"  Confidence: {judgment['confidence']:.0%}")
            print(f"  Reasoning: {judgment['reasoning']}")
            print("  Decisive evidence:")
            for item in judgment["decisive_evidence"]:
                print(f"    - {item}")
            if judgment["blocking_uncertainties"]:
                print("  Blocking uncertainties:")
                for item in judgment["blocking_uncertainties"]:
                    print(f"    - {item}")
            print("  Decision criteria:")
            for criterion in judgment["decision_criteria"]:
                print(f"    - [{criterion['status'].upper()}] {criterion['criterion']}")
                print(f"      Evidence: {criterion['evidence']}")
        recommendation = result.get("recommendation")
        if recommendation:
            print("\nRecommendation:")
            print(f"  Decision preserved: {recommendation['decision']}")
            print(f"  Direction: {recommendation['recommended_direction']}")
            print("  Next actions:")
            for number, action in enumerate(recommendation["next_actions"], start=1):
                print(f"    {number}. {action['action']}")
                print(f"       Purpose: {action['purpose']}")
                print(f"       Done when: {action['completion_criterion']}")
            if recommendation["validation_experiments"]:
                print("  Validation experiments:")
                for experiment in recommendation["validation_experiments"]:
                    print(f"    - Hypothesis: {experiment['hypothesis']}")
                    print(f"      Method: {experiment['method']}")
                    print(f"      Success: {experiment['success_criterion']}")
                    print(f"      Failure: {experiment['failure_signal']}")
            sections = (
                ("Build now", "build_now"),
                ("Do not build yet", "do_not_build_yet"),
                ("Evidence used", "evidence_used"),
                ("Unresolved questions", "unresolved_questions"),
                ("Human review questions", "human_review_questions"),
            )
            for label, key in sections:
                if recommendation[key]:
                    print(f"  {label}:")
                    for item in recommendation[key]:
                        print(f"    - {item}")
        if result.get("status") == "review_complete":
            print("\nHuman review complete:")
            print(f"  Action: {result['review_action'].upper()}")
            print(f"  Notes: {result.get('review_notes') or 'None'}")
            if result.get("evaluation_saved"):
                print(f"  Saved evaluation ID: {result.get('evaluation_id')}")
        if result.get("status") == "evaluation_reused":
            print("\nPrior evaluation reused; research APIs were not called.")
            print(f"  Evaluation ID: {result.get('reused_from_evaluation_id')}")
        if prompt and prompt.get("choices"):
            print(f"\n{prompt['question']}")
            if prompt.get("decision"):
                print(f"Prior decision: {prompt['decision']}")
                print(f"Prior review: {prompt.get('review_action')}")
                print(f"Created: {prompt.get('created_at')}")
            print(f"Choices: {', '.join(prompt['choices'])}")
            if prompt.get("kind") == "prior_evaluation":
                print("Resume with --prior reuse or --prior refresh.")
            else:
                print("Resume with --review CHOICE and optional --notes TEXT.")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Build or Bust — Stages 1–8")
    parser.add_argument("idea", nargs="?", help="Product idea to normalize")
    parser.add_argument("--thread", default=str(uuid.uuid4()), help="Persistent run ID")
    resume_options = parser.add_mutually_exclusive_group()
    resume_options.add_argument("--resume", help="Answer a saved clarification question")
    resume_options.add_argument(
        "--review", choices=("approve", "reject"), help="Resume human review"
    )
    resume_options.add_argument(
        "--prior", choices=("reuse", "refresh"), help="Reuse or refresh a prior evaluation"
    )
    parser.add_argument("--notes", default="", help="Optional human-review notes")
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
        elif args.review is not None:
            request = Command(resume={"action": args.review, "notes": args.notes})
            result = graph.invoke(request, config=config)
        elif args.prior is not None:
            request = Command(resume={"action": args.prior})
            result = graph.invoke(request, config=config)
        else:
            request = Command(resume=args.resume) if args.resume is not None else {
                "raw_input": args.idea or "", "status": "pending", "thread_id": args.thread
            }
            result = graph.invoke(request, config=config)
        print(f"Thread: {args.thread}")
        _show(result)


if __name__ == "__main__":
    main()
