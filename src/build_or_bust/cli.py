import argparse
import os
import uuid

from dotenv import load_dotenv
from langgraph.types import Command

from .graph import open_graph


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
            for source in result.get("research_sources", []):
                print(f"    - {source['title']}: {source['url']}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Build or Bust — Stages 1–2")
    parser.add_argument("idea", nargs="?", help="Product idea to normalize")
    parser.add_argument("--thread", default=str(uuid.uuid4()), help="Persistent run ID")
    parser.add_argument("--resume", help="Answer a saved clarification question")
    args = parser.parse_args()

    config = {"configurable": {"thread_id": args.thread}}
    with open_graph(os.getenv("CHECKPOINT_DB", "build_or_bust.db")) as graph:
        request = Command(resume=args.resume) if args.resume is not None else {
            "raw_input": args.idea or "", "status": "pending"
        }
        result = graph.invoke(request, config=config)
        print(f"Thread: {args.thread}")
        _show(result)


if __name__ == "__main__":
    main()
