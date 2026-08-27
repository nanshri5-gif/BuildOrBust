from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from build_or_bust.consumer_research import ConsumerResearch, ResearchFailure
from build_or_bust.extractor import ExtractionFailure, IntakeData
from build_or_bust.graph import build_graph


class FakeExtractor:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    def extract(self, user_text):
        self.calls += 1
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


class FakeResearcher:
    def __init__(self, output=None):
        self.output = output or (
            ConsumerResearch(
                summary="Parents need simpler meal planning.",
                pain_points=["Planning takes time"],
                current_behaviors=["Use handwritten lists"],
                evidence_gaps=["Willingness to pay is unknown"],
            ),
            [{"title": "Consumer study", "url": "https://example.com/study"}],
        )
        self.calls = 0

    def research(self, state):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def complete_data(**changes):
    values = {
        "product_idea": "A meal-planning app",
        "target_customer": "Busy parents",
        "geography": "United States",
        "problem": "Planning weeknight meals takes too long",
        "product_type": "Mobile app",
    }
    values.update(changes)
    return IntakeData(**values)


def config(thread="test-thread"):
    return {"configurable": {"thread_id": thread}}


def test_missing_input_does_not_call_openai():
    extractor = FakeExtractor([])
    result = build_graph(extractor, FakeResearcher(), InMemorySaver()).invoke(
        {"raw_input": ""}, config=config()
    )
    assert result["error_code"] == "missing_user_input"
    assert extractor.calls == 0


def test_complete_intake_runs_consumer_research():
    researcher = FakeResearcher()
    result = build_graph(FakeExtractor([complete_data()]), researcher, InMemorySaver()).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "research_complete"
    assert result["missing_fields"] == []
    assert result["consumer_research"]["pain_points"] == ["Planning takes time"]
    assert result["research_sources"][0]["url"] == "https://example.com/study"
    assert researcher.calls == 1


def test_missing_fields_interrupt_and_resume():
    extractor = FakeExtractor([
        complete_data(geography=None),
        complete_data(geography="Canada"),
    ])
    graph = build_graph(extractor, FakeResearcher(), InMemorySaver())
    first = graph.invoke({"raw_input": "idea"}, config=config())
    assert first["__interrupt__"][0].value["missing_fields"] == ["geography"]
    resumed = graph.invoke(Command(resume="Launch in Canada"), config=config())
    assert resumed["status"] == "research_complete"
    assert resumed["geography"] == "Canada"
    assert extractor.calls == 2


def test_api_failure_is_explicit():
    failure = ExtractionFailure("openai_api_failure", "request failed")
    result = build_graph(FakeExtractor([failure]), FakeResearcher(), InMemorySaver()).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "error"
    assert result["error_code"] == "openai_api_failure"


def test_malformed_output_is_explicit():
    failure = ExtractionFailure("malformed_output", "bad structure")
    result = build_graph(FakeExtractor([failure]), FakeResearcher(), InMemorySaver()).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "error"
    assert result["error_code"] == "malformed_output"


def test_consumer_research_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(ResearchFailure("search failed")),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "consumer_research_failure"
