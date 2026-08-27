from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from build_or_bust.assumption_killer import (
    AssumptionAnalysis,
    AssumptionKillerFailure,
    CriticalAssumption,
    OpenAIAssumptionKiller,
)
from build_or_bust.competitor_research import (
    Competitor,
    CompetitorResearch,
    CompetitorResearchFailure,
)
from build_or_bust.consumer_research import ConsumerResearch, ResearchFailure, _sources
from build_or_bust.extractor import ExtractionFailure, IntakeData
from build_or_bust.cli import _show_sources
from build_or_bust.graph import build_graph
from build_or_bust.market_feasibility import (
    MarketFeasibilityFailure,
    MarketFeasibilityResearch,
)


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


class FakeCompetitorResearcher:
    def __init__(self, output=None):
        self.output = output or (
            CompetitorResearch(
                summary="Several meal-planning apps serve busy families.",
                direct_competitors=[
                    Competitor(
                        name="Meal App",
                        offering="Weekly meal plans and grocery lists",
                        pricing="$5/month",
                        strengths=["Simple planning"],
                        weaknesses=["Limited customization"],
                    )
                ],
                alternatives=["Handwritten meal plans"],
                differentiation_gaps=["Family collaboration"],
                evidence_gaps=["Current subscriber count is unknown"],
            ),
            [{"title": "Meal App pricing", "url": "https://example.com/pricing"}],
        )
        self.calls = 0

    def research(self, state):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class FakeMarketFeasibilityResearcher:
    def __init__(self, output=None):
        self.output = output or (
            MarketFeasibilityResearch(
                summary="Demand exists, with manageable implementation dependencies.",
                demand_signals=["Parents report recurring planning burden"],
                market_proxies=["Meal-planning tools have paid subscribers"],
                adoption_constraints=["Families may resist maintaining preferences"],
                technical_dependencies=["Recipe and nutrition data"],
                feasibility_risks=["Recommendations may not satisfy every family member"],
                evidence_gaps=["Willingness to pay is not established"],
            ),
            [{"title": "Market evidence", "url": "https://example.com/market"}],
        )
        self.calls = 0

    def research(self, state):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def fake_assumption(statement: str, category: str = "consumer"):
    return CriticalAssumption(
        statement=statement,
        category=category,
        evidence_for=["Consumer research supports this"],
        evidence_against=["Willingness to pay is unknown"],
        evidence_strength="mixed",
        impact_if_false="high",
        validation_experiment="Interview 10 target users",
        success_criterion="At least 7 describe the problem unprompted",
    )


class FakeAssumptionKiller:
    def __init__(self, output=None):
        self.output = output or AssumptionAnalysis(
            summary="The idea depends on several unproven assumptions.",
            critical_assumptions=[
                fake_assumption("Parents want automated planning"),
                fake_assumption("The product can differentiate", "competitive"),
                fake_assumption("Required data is available", "technical"),
            ],
            contradictions=["Demand exists but willingness to pay is unknown"],
            fatal_risks=["Families may reject generated meals"],
            unresolved_questions=["Will parents maintain preference profiles?"],
        )
        self.calls = 0

    def analyze(self, state):
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
    result = build_graph(
        extractor,
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        InMemorySaver(),
    ).invoke(
        {"raw_input": ""}, config=config()
    )
    assert result["error_code"] == "missing_user_input"
    assert extractor.calls == 0


def test_complete_intake_runs_both_research_stages():
    researcher = FakeResearcher()
    competitor_researcher = FakeCompetitorResearcher()
    market_researcher = FakeMarketFeasibilityResearcher()
    assumption_killer = FakeAssumptionKiller()
    result = build_graph(
        FakeExtractor([complete_data()]),
        researcher,
        competitor_researcher,
        market_researcher,
        assumption_killer,
        InMemorySaver(),
    ).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "assumption_analysis_complete"
    assert result["missing_fields"] == []
    assert result["consumer_research"]["pain_points"] == ["Planning takes time"]
    assert result["research_sources"][0]["url"] == "https://example.com/study"
    assert researcher.calls == 1
    assert result["competitor_research"]["direct_competitors"][0]["name"] == "Meal App"
    assert result["competitor_sources"][0]["url"] == "https://example.com/pricing"
    assert competitor_researcher.calls == 1
    assert result["market_feasibility_research"]["demand_signals"] == [
        "Parents report recurring planning burden"
    ]
    assert result["market_feasibility_sources"][0]["url"] == "https://example.com/market"
    assert market_researcher.calls == 1
    assert len(result["assumption_analysis"]["critical_assumptions"]) == 3
    assert assumption_killer.calls == 1


def test_missing_fields_interrupt_and_resume():
    extractor = FakeExtractor([
        complete_data(geography=None),
        complete_data(geography="Canada"),
    ])
    graph = build_graph(
        extractor,
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        InMemorySaver(),
    )
    first = graph.invoke({"raw_input": "idea"}, config=config())
    assert first["__interrupt__"][0].value["missing_fields"] == ["geography"]
    resumed = graph.invoke(Command(resume="Launch in Canada"), config=config())
    assert resumed["status"] == "assumption_analysis_complete"
    assert resumed["geography"] == "Canada"
    assert extractor.calls == 2


def test_api_failure_is_explicit():
    failure = ExtractionFailure("openai_api_failure", "request failed")
    result = build_graph(
        FakeExtractor([failure]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        InMemorySaver(),
    ).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "error"
    assert result["error_code"] == "openai_api_failure"


def test_malformed_output_is_explicit():
    failure = ExtractionFailure("malformed_output", "bad structure")
    result = build_graph(
        FakeExtractor([failure]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        InMemorySaver(),
    ).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "error"
    assert result["error_code"] == "malformed_output"


def test_consumer_research_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(ResearchFailure("search failed")),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "consumer_research_failure"


def test_competitor_research_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(CompetitorResearchFailure("search failed")),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "competitor_research_failure"


def test_market_feasibility_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(MarketFeasibilityFailure("search failed")),
        FakeAssumptionKiller(),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "market_feasibility_failure"


def test_assumption_killer_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(AssumptionKillerFailure("analysis failed")),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "assumption_killer_failure"


def test_assumption_killer_does_not_receive_web_search_tool():
    report = FakeAssumptionKiller().output

    class FakeResponses:
        def __init__(self):
            self.arguments = None

        def parse(self, **kwargs):
            self.arguments = kwargs
            return SimpleNamespace(output_parsed=report)

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    result = OpenAIAssumptionKiller(client=client, model="test-model").analyze(
        {
            "product_idea": "idea",
            "target_customer": "customer",
            "geography": "place",
            "problem": "problem",
            "product_type": "app",
            "consumer_research": {},
            "competitor_research": {},
            "market_feasibility_research": {},
        }
    )
    assert result == report
    assert "tools" not in responses.arguments


def test_sources_traverses_objects_without_serializing_entire_response():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                action=SimpleNamespace(
                    sources=[
                        SimpleNamespace(title="Study", url="https://example.com/study"),
                        SimpleNamespace(title="Duplicate", url="https://example.com/study"),
                    ]
                )
            ),
            SimpleNamespace(content="A parsed output message without an action"),
        ]
    )
    assert _sources(response) == [
        {"title": "Study", "url": "https://example.com/study"}
    ]


def test_cli_limits_displayed_sources_but_reports_remainder(capsys):
    sources = [
        {"title": f"Source {number}", "url": f"https://example.com/{number}"}
        for number in range(12)
    ]
    _show_sources(sources)
    output = capsys.readouterr().out
    assert "Source 9" in output
    assert "Source 10" not in output
    assert "2 more sources saved in the checkpoint" in output
