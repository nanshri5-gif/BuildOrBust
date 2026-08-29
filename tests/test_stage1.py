from types import SimpleNamespace
import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from build_or_bust.assumption_killer import (
    AssumptionAnalysis,
    AssumptionKillerFailure,
    CriticalAssumption,
    NebiusAssumptionKiller,
)
from build_or_bust.competitor_research import (
    Competitor,
    CompetitorResearch,
    CompetitorResearchFailure,
    YouMCPCompetitorResearcher,
)
from build_or_bust.consumer_research import (
    ConsumerResearch,
    ResearchFailure,
    SearchHit,
    YouMCPClient,
    YouMCPConsumerResearcher,
    _find_hits,
)
from build_or_bust.extractor import ExtractionFailure, IntakeData, NebiusExtractor
from build_or_bust.cli import _show_sources
from build_or_bust.graph import build_graph
from build_or_bust.judge import (
    DecisionCriterion,
    JudgeFailure,
    Judgment,
    NebiusJudge,
)
from build_or_bust.idea_registry import SQLiteIdeaRegistry
from build_or_bust.market_feasibility import (
    MarketFeasibilityFailure,
    MarketFeasibilityResearch,
    YouMCPMarketFeasibilityResearcher,
)
from build_or_bust.recommendation import (
    NebiusRecommendationAgent,
    Recommendation,
    RecommendationFailure,
    RecommendedAction,
    ValidationExperiment,
)
from build_or_bust.search_query import bounded_query
from build_or_bust.dashboard import confidence_chart_data
from build_or_bust.ui import checkpoint_result, public_demo_mode


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
            [
                {"title": "Consumer study", "url": "https://example.com/study"},
                {"title": "Parent survey", "url": "https://research.org/parents"},
                {"title": "Time-use data", "url": "https://research.org/time-use"},
            ],
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
            [
                {
                    "title": "Meal App pricing",
                    "url": "https://mealapp.com/pricing",
                    "content_extracted": True,
                },
                {
                    "title": "Competitor review",
                    "url": "https://reviews.org/meal-app",
                    "content_extracted": False,
                },
            ],
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
            [
                {"title": "Market evidence", "url": "https://example.com/market"},
                {"title": "Adoption study", "url": "https://research.org/adoption"},
                {"title": "Technical review", "url": "https://research.org/technical"},
            ],
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


class FakeJudge:
    def __init__(self, output=None):
        self.output = output or Judgment(
            decision="VALIDATE",
            confidence=0.72,
            reasoning="The problem appears real, but key commercial assumptions remain open.",
            decisive_evidence=["Parents report a recurring planning burden"],
            blocking_uncertainties=["Willingness to pay is unknown"],
            decision_criteria=[
                DecisionCriterion(
                    criterion="Problem evidence",
                    status="supported",
                    evidence="Consumer research identifies recurring planning burden.",
                ),
                DecisionCriterion(
                    criterion="Differentiation",
                    status="unknown",
                    evidence="Competitor research identifies an untested collaboration gap.",
                ),
                DecisionCriterion(
                    criterion="Commercial demand",
                    status="unknown",
                    evidence="Willingness to pay has not been established.",
                ),
            ],
        )
        self.calls = 0

    def decide(self, state):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class FakeRecommendationAgent:
    def __init__(self, output=None):
        self.output = output or Recommendation(
            decision="VALIDATE",
            recommended_direction="Validate demand before building the product.",
            next_actions=[
                RecommendedAction(
                    action="Interview target parents",
                    purpose="Test the severity and frequency of the problem",
                    completion_criterion="Complete 10 structured interviews",
                )
            ],
            validation_experiments=[
                ValidationExperiment(
                    hypothesis="Parents will repeatedly use an automated weekly plan",
                    method="Run a two-week concierge meal-planning trial",
                    success_criterion="At least 7 of 10 families use both weekly plans",
                    failure_signal="Fewer than 4 families use the second weekly plan",
                )
            ],
            build_now=["A manual concierge trial and simple signup page"],
            do_not_build_yet=["A full mobile application"],
            evidence_used=["Consumer research shows recurring planning burden"],
            unresolved_questions=["Willingness to pay remains unknown"],
            human_review_questions=["What budget is available for validation?"],
        )
        self.calls = 0
        self.states = []

    def recommend(self, state):
        self.calls += 1
        self.states.append(dict(state))
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


def test_search_query_is_normalized_and_bounded():
    query = bounded_query("  physical   product ", "feature " * 200)
    assert len(query) <= 500
    assert "  " not in query
    assert not query.endswith(" ")


def test_confidence_chart_keeps_evidence_readiness_separate_from_judge_confidence():
    rows = confidence_chart_data(
        {
            "evidence_assessment": {
                "source_counts": {"consumer": 3, "competitor": 2, "market": 3},
                "independent_domain_counts": {
                    "consumer": 2,
                    "competitor": 2,
                    "market": 2,
                },
                "extracted_page_counts": {"competitor": 0},
                "coverage": {
                    "consumer_pain_points": True,
                    "consumer_current_behaviors": True,
                    "direct_competitors": True,
                    "existing_alternatives": True,
                    "market_demand_signals": True,
                    "market_proxies": True,
                    "adoption_constraints": True,
                    "technical_dependencies": True,
                    "feasibility_risks": True,
                },
            },
            "judgment": {"confidence": 0.75},
        }
    )
    scores = {row["Measure"]: row["Percent"] for row in rows}
    assert scores["Consumer evidence readiness"] == 100
    assert scores["Competitor evidence readiness"] == 0
    assert scores["Market evidence readiness"] == 100
    assert scores["Judge confidence"] == 75


def test_checkpoint_result_restores_pending_interrupts():
    pending = SimpleNamespace(value={"question": "Please clarify geography"})
    snapshot = SimpleNamespace(
        values={"status": "needs_clarification", "product_idea": "Idea"},
        tasks=(SimpleNamespace(interrupts=(pending,)),),
    )
    result = checkpoint_result(snapshot)
    assert result["status"] == "needs_clarification"
    assert result["__interrupt__"] == (pending,)


def test_public_demo_mode_reads_truthy_environment_values(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    assert public_demo_mode() is True


def test_public_demo_mode_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("PUBLIC_DEMO_MODE", raising=False)
    assert public_demo_mode() is False


def test_missing_input_does_not_call_model_provider():
    extractor = FakeExtractor([])
    result = build_graph(
        extractor,
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
    ).invoke(
        {"raw_input": ""}, config=config()
    )
    assert result["error_code"] == "missing_user_input"
    assert extractor.calls == 0


def test_complete_flow_pauses_for_review_and_can_be_approved():
    researcher = FakeResearcher()
    competitor_researcher = FakeCompetitorResearcher()
    market_researcher = FakeMarketFeasibilityResearcher()
    assumption_killer = FakeAssumptionKiller()
    judge = FakeJudge()
    recommendation_agent = FakeRecommendationAgent()
    graph = build_graph(
        FakeExtractor([complete_data()]),
        researcher,
        competitor_researcher,
        market_researcher,
        assumption_killer,
        judge,
        InMemorySaver(),
        recommendation_agent=recommendation_agent,
    )
    first = graph.invoke({"raw_input": "idea"}, config=config())
    assert first["__interrupt__"][0].value["choices"] == [
        "approve",
        "revise",
        "reject",
    ]
    result = graph.invoke(
        Command(resume={"action": "approve", "notes": "Proceed with validation"}),
        config=config(),
    )
    assert result["status"] == "review_complete"
    assert result["missing_fields"] == []
    assert result["consumer_research"]["pain_points"] == ["Planning takes time"]
    assert result["research_sources"][0]["url"] == "https://example.com/study"
    assert researcher.calls == 1
    assert result["competitor_research"]["direct_competitors"][0]["name"] == "Meal App"
    assert result["competitor_sources"][0]["url"] == "https://mealapp.com/pricing"
    assert competitor_researcher.calls == 1
    assert result["market_feasibility_research"]["demand_signals"] == [
        "Parents report recurring planning burden"
    ]
    assert result["market_feasibility_sources"][0]["url"] == "https://example.com/market"
    assert market_researcher.calls == 1
    assert len(result["assumption_analysis"]["critical_assumptions"]) == 3
    assert assumption_killer.calls == 1
    assert result["judgment"]["decision"] == "VALIDATE"
    assert judge.calls == 1
    assert result["evidence_assessment"]["sufficient"] is True
    assert result["recommendation"]["decision"] == "VALIDATE"
    assert recommendation_agent.calls == 1
    assert result["review_action"] == "approve"
    assert result["review_notes"] == "Proceed with validation"


def test_review_revision_regenerates_only_recommendation_then_pauses_again():
    recommendation_agent = FakeRecommendationAgent()
    graph = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=recommendation_agent,
    )
    review_config = config("revise-recommendation")
    graph.invoke({"raw_input": "idea"}, config=review_config)
    revised = graph.invoke(
        Command(
            resume={
                "action": "revise",
                "notes": "Make the first experiment cheaper and one week long.",
            }
        ),
        config=review_config,
    )

    assert revised["__interrupt__"]
    assert recommendation_agent.calls == 2
    assert recommendation_agent.states[1]["review_feedback"] == (
        "Make the first experiment cheaper and one week long."
    )
    approved = graph.invoke(
        Command(resume={"action": "approve", "notes": "Revision accepted"}),
        config=review_config,
    )
    assert approved["status"] == "review_complete"
    assert approved["recommendation_revision_count"] == 1
    assert [item["action"] for item in approved["review_history"]] == [
        "revise",
        "approve",
    ]


def test_review_revision_limit_stops_the_loop():
    graph = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=FakeRecommendationAgent(),
    )
    review_config = config("revision-limit")
    graph.invoke({"raw_input": "idea"}, config=review_config)
    for number in range(2):
        graph.invoke(
            Command(resume={"action": "revise", "notes": f"Revision {number}"}),
            config=review_config,
        )
    stopped = graph.invoke(
        Command(resume={"action": "revise", "notes": "One more revision"}),
        config=review_config,
    )
    assert stopped["status"] == "error"
    assert stopped["error_code"] == "revision_limit_reached"


def test_approved_evaluation_can_be_reused_without_research(tmp_path):
    registry_path = tmp_path / "registry.db"
    registry = SQLiteIdeaRegistry(registry_path)
    first_graph = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=FakeRecommendationAgent(),
        idea_registry=registry,
    )
    first_config = config("original-evaluation")
    first_graph.invoke(
        {"raw_input": "idea", "thread_id": "original-evaluation"},
        config=first_config,
    )
    saved = first_graph.invoke(
        Command(resume={"action": "approve", "notes": "Approved"}),
        config=first_config,
    )
    assert saved["status"] == "review_complete"
    assert saved["evaluation_saved"] is True

    researcher = FakeResearcher()
    competitor = FakeCompetitorResearcher()
    market = FakeMarketFeasibilityResearcher()
    second_graph = build_graph(
        FakeExtractor([complete_data()]),
        researcher,
        competitor,
        market,
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=FakeRecommendationAgent(),
        idea_registry=registry,
    )
    second_config = config("reuse-evaluation")
    match = second_graph.invoke(
        {"raw_input": "same idea", "thread_id": "reuse-evaluation"},
        config=second_config,
    )
    assert match["__interrupt__"][0].value["choices"] == ["reuse", "refresh"]
    reused = second_graph.invoke(
        Command(resume={"action": "reuse"}), config=second_config
    )

    assert reused["status"] == "evaluation_reused"
    assert reused["judgment"]["decision"] == "VALIDATE"
    assert reused["reused_from_evaluation_id"] == saved["evaluation_id"]
    assert researcher.calls == 0
    assert competitor.calls == 0
    assert market.calls == 0
    history = registry.list_recent()
    assert len(history) == 1
    assert history[0].evaluation_id == saved["evaluation_id"]
    assert history[0].intake["product_idea"] == "A meal-planning app"
    assert history[0].decision == "VALIDATE"
    with sqlite3.connect(registry_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM idea_evaluations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM evaluation_sources").fetchone()[0] == 8
        assert connection.execute("SELECT COUNT(*) FROM evaluation_reviews").fetchone()[0] == 1


def test_prior_evaluation_refresh_runs_research(tmp_path):
    registry = SQLiteIdeaRegistry(tmp_path / "refresh.db")
    seed_graph = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=FakeRecommendationAgent(),
        idea_registry=registry,
    )
    seed_config = config("refresh-seed")
    seed_graph.invoke({"raw_input": "idea"}, config=seed_config)
    seed_graph.invoke(
        Command(resume={"action": "reject", "notes": "Not now"}),
        config=seed_config,
    )

    researcher = FakeResearcher()
    refresh_graph = build_graph(
        FakeExtractor([complete_data()]),
        researcher,
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=FakeRecommendationAgent(),
        idea_registry=registry,
    )
    refresh_config = config("refresh-run")
    refresh_graph.invoke({"raw_input": "idea"}, config=refresh_config)
    refreshed = refresh_graph.invoke(
        Command(resume={"action": "refresh"}), config=refresh_config
    )

    assert refreshed["__interrupt__"]
    assert researcher.calls == 1


def test_weak_evidence_stops_before_assumption_killer_and_judge():
    weak_consumer = FakeResearcher()
    weak_consumer.output = (
        weak_consumer.output[0],
        [{"title": "Only source", "url": "https://example.com/study"}],
    )
    assumption_killer = FakeAssumptionKiller()
    judge = FakeJudge()
    recommendation_agent = FakeRecommendationAgent()

    result = build_graph(
        FakeExtractor([complete_data()]),
        weak_consumer,
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        assumption_killer,
        judge,
        InMemorySaver(),
        recommendation_agent=recommendation_agent,
    ).invoke({"raw_input": "idea"}, config=config("weak-evidence"))

    assert result["status"] == "insufficient_evidence"
    assert result["evidence_assessment"]["sufficient"] is False
    assert any(
        "consumer needs at least 3 valid unique sources" in check
        for check in result["evidence_assessment"]["failed_checks"]
    )
    assert assumption_killer.calls == 0
    assert judge.calls == 0
    assert recommendation_agent.calls == 0


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
        FakeJudge(),
        InMemorySaver(),
    )
    first = graph.invoke({"raw_input": "idea"}, config=config())
    assert first["__interrupt__"][0].value["missing_fields"] == ["geography"]
    resumed = graph.invoke(Command(resume="Launch in Canada"), config=config())
    assert resumed["status"] == "judgment_complete"
    assert resumed["geography"] == "Canada"
    assert extractor.calls == 2


def test_api_failure_is_explicit():
    failure = ExtractionFailure("nebius_api_failure", "request failed")
    result = build_graph(
        FakeExtractor([failure]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
    ).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "error"
    assert result["error_code"] == "nebius_api_failure"


def test_malformed_output_is_explicit():
    failure = ExtractionFailure("malformed_output", "bad structure")
    result = build_graph(
        FakeExtractor([failure]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
    ).invoke(
        {"raw_input": "idea"}, config=config()
    )
    assert result["status"] == "error"
    assert result["error_code"] == "malformed_output"


def test_nebius_extractor_requests_json_schema_and_validates_response():
    class FakeCompletions:
        def __init__(self):
            self.arguments = None

        def create(self, **kwargs):
            self.arguments = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=complete_data().model_dump_json(), refusal=None
                        )
                    )
                ]
            )

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = NebiusExtractor(client=client, model="test-model").extract("idea")

    assert result == complete_data()
    assert completions.arguments["response_format"]["type"] == "json_schema"
    assert completions.arguments["response_format"]["json_schema"]["strict"] is True
    assert completions.arguments["messages"][1]["content"] == "idea"


def test_nebius_extractor_rejects_invalid_json():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="not-json", refusal=None)
                        )
                    ]
                )
            )
        )
    )

    try:
        NebiusExtractor(client=client, model="test-model").extract("idea")
    except ExtractionFailure as exc:
        assert exc.code == "malformed_output"
    else:
        raise AssertionError("Invalid JSON should fail intake extraction")


def test_consumer_research_failure_is_explicit():
    judge = FakeJudge()
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(ResearchFailure("search failed")),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        judge,
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "consumer_research_failure"
    assert judge.calls == 0


def test_competitor_research_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(CompetitorResearchFailure("search failed")),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
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
        FakeJudge(),
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
        FakeJudge(),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "assumption_killer_failure"


def test_judge_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(JudgeFailure("judgment failed")),
        InMemorySaver(),
    ).invoke({"raw_input": "idea"}, config=config())
    assert result["status"] == "error"
    assert result["error_code"] == "judge_failure"


def test_recommendation_failure_is_explicit():
    result = build_graph(
        FakeExtractor([complete_data()]),
        FakeResearcher(),
        FakeCompetitorResearcher(),
        FakeMarketFeasibilityResearcher(),
        FakeAssumptionKiller(),
        FakeJudge(),
        InMemorySaver(),
        recommendation_agent=FakeRecommendationAgent(
            RecommendationFailure("recommendation failed")
        ),
    ).invoke({"raw_input": "idea"}, config=config("recommendation-failure"))
    assert result["status"] == "error"
    assert result["error_code"] == "recommendation_failure"


def test_nebius_recommendation_preserves_judges_decision_and_uses_no_tools():
    recommendation = FakeRecommendationAgent().output

    class FakeCompletions:
        def __init__(self):
            self.arguments = None

        def create(self, **kwargs):
            self.arguments = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=recommendation.model_dump_json(), refusal=None
                        )
                    )
                ]
            )

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = NebiusRecommendationAgent(client=client, model="test-model").recommend(
        {"judgment": FakeJudge().output.model_dump()}
    )
    assert result == recommendation
    assert "tools" not in completions.arguments
    assert completions.arguments["response_format"]["type"] == "json_schema"
    assert completions.arguments["response_format"]["json_schema"]["strict"] is True


def test_nebius_recommendation_rejects_changed_decision():
    changed = FakeRecommendationAgent().output.model_copy(update={"decision": "BUILD"})
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=changed.model_dump_json(), refusal=None
                            )
                        )
                    ]
                )
            )
        )
    )
    try:
        NebiusRecommendationAgent(client=client, model="test-model").recommend(
            {"judgment": FakeJudge().output.model_dump()}
        )
    except RecommendationFailure as exc:
        assert exc.code == "decision_mismatch"
    else:
        raise AssertionError("Recommendation must not change the Judge's decision")


def test_nebius_judge_uses_schema_without_tools():
    judgment = FakeJudge().output

    class FakeCompletions:
        def __init__(self):
            self.arguments = None

        def create(self, **kwargs):
            self.arguments = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=judgment.model_dump_json(), refusal=None
                        )
                    )
                ]
            )

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = NebiusJudge(client=client, model="test-model").decide(
        {
            "product_idea": "idea",
            "target_customer": "customer",
            "geography": "place",
            "problem": "problem",
            "product_type": "app",
            "consumer_research": {},
            "competitor_research": {},
            "market_feasibility_research": {},
            "assumption_analysis": {},
        }
    )
    assert result == judgment
    assert "tools" not in completions.arguments
    assert completions.arguments["response_format"]["type"] == "json_schema"
    assert completions.arguments["response_format"]["json_schema"]["strict"] is True


def test_nebius_judge_rejects_malformed_json():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="not-json", refusal=None)
                        )
                    ]
                )
            )
        )
    )
    try:
        NebiusJudge(client=client, model="test-model").decide({})
    except JudgeFailure as exc:
        assert exc.code == "malformed_output"
    else:
        raise AssertionError("Malformed Nebius JSON should fail judgment")


def test_nebius_assumption_killer_uses_schema_without_tools():
    report = FakeAssumptionKiller().output

    class FakeCompletions:
        def __init__(self):
            self.arguments = None

        def create(self, **kwargs):
            self.arguments = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=report.model_dump_json(), refusal=None
                        )
                    )
                ]
            )

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = NebiusAssumptionKiller(client=client, model="test-model").analyze(
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
    assert "tools" not in completions.arguments
    assert completions.arguments["response_format"]["type"] == "json_schema"
    assert completions.arguments["response_format"]["json_schema"]["strict"] is True


def test_nebius_assumption_killer_rejects_malformed_json():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="not-json", refusal=None)
                        )
                    ]
                )
            )
        )
    )
    try:
        NebiusAssumptionKiller(client=client, model="test-model").analyze({})
    except AssumptionKillerFailure as exc:
        assert exc.code == "malformed_output"
    else:
        raise AssertionError("Malformed Nebius JSON should fail assumption analysis")


def test_find_hits_accepts_nested_you_search_results():
    payload = {
        "results": {
            "web": [
                {
                    "title": "Study",
                    "url": "https://example.com/study",
                    "snippets": ["Parents report planning fatigue."],
                }
            ]
        }
    }
    assert _find_hits(payload) == [
        SearchHit(
            title="Study",
            url="https://example.com/study",
            snippets=["Parents report planning fatigue."],
        )
    ]


def test_consumer_research_uses_mcp_evidence_and_nebius_schema():
    class FakeSearchClient:
        def __init__(self):
            self.query = None

        def search(self, query):
            self.query = query
            return [
                SearchHit(
                    title="Consumer study",
                    url="https://example.com/study",
                    snippets=["Planning takes time."],
                )
            ]

    class FakeCompletions:
        def __init__(self):
            self.arguments = None

        def create(self, **kwargs):
            self.arguments = kwargs
            report = ConsumerResearch(
                summary="Parents need simpler planning.",
                pain_points=["Planning takes time"],
                current_behaviors=["Use handwritten lists"],
                evidence_gaps=["Willingness to pay is unknown"],
            )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=report.model_dump_json(), refusal=None
                        )
                    )
                ]
            )

    search_client = FakeSearchClient()
    completions = FakeCompletions()
    model_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    report, sources = YouMCPConsumerResearcher(
        search_client=search_client,
        model_client=model_client,
        model="test-model",
    ).research(complete_data().model_dump())

    assert "Busy parents" in search_client.query
    assert report.pain_points == ["Planning takes time"]
    assert sources == [
        {"title": "Consumer study", "url": "https://example.com/study"}
    ]
    assert completions.arguments["response_format"]["type"] == "json_schema"
    assert "You.com MCP evidence" in completions.arguments["messages"][1]["content"]


def test_competitor_research_uses_mcp_search_and_page_contents():
    class FakeEvidenceClient:
        def __init__(self):
            self.query = None
            self.content_urls = []

        def search(self, query):
            self.query = query
            return [
                SearchHit(
                    title="Meal App pricing",
                    url="https://example.com/pricing",
                    snippets=["Meal App offers weekly plans."],
                )
            ]

        def contents(self, url):
            self.content_urls.append(url)
            return "# Pricing\n$5 per month"

    class FakeCompletions:
        def __init__(self):
            self.arguments = None

        def create(self, **kwargs):
            self.arguments = kwargs
            report = FakeCompetitorResearcher().output[0]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=report.model_dump_json(), refusal=None
                        )
                    )
                ]
            )

    evidence_client = FakeEvidenceClient()
    completions = FakeCompletions()
    model_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    state = complete_data().model_dump()
    state["consumer_research"] = {"summary": "Parents need simpler planning."}
    report, sources = YouMCPCompetitorResearcher(
        evidence_client=evidence_client,
        model_client=model_client,
        model="test-model",
    ).research(state)

    assert "competitors alternatives pricing" in evidence_client.query
    assert evidence_client.content_urls == ["https://example.com/pricing"]
    assert report.direct_competitors[0].name == "Meal App"
    assert sources == [
        {
            "title": "Meal App pricing",
            "url": "https://example.com/pricing",
            "content_extracted": True,
        }
    ]
    prompt = completions.arguments["messages"][1]["content"]
    assert "$5 per month" in prompt
    assert completions.arguments["response_format"]["type"] == "json_schema"


def test_you_contents_sends_urls_as_an_array():
    client = YouMCPClient(api_key="test-key")
    captured = {}

    async def fake_call_tool(name, arguments):
        captured["name"] = name
        captured["arguments"] = arguments
        return SimpleNamespace(
            content=[SimpleNamespace(text='{"content": "extracted page"}')]
        )

    client._call_tool = fake_call_tool
    result = client.contents("https://example.com/page")

    assert result == "extracted page"
    assert captured == {
        "name": "you-contents",
        "arguments": {"urls": ["https://example.com/page"]},
    }


def test_market_research_uses_mcp_structured_research():
    class FakeMarketResearchClient:
        def __init__(self):
            self.question = None
            self.schema = None

        def research(self, question, output_schema):
            self.question = question
            self.schema = output_schema
            report = FakeMarketFeasibilityResearcher().output[0]
            content = report.model_dump()
            content["demand_signals"] = [f"Signal {number}" for number in range(6)]
            return content, [
                {"title": "Market evidence", "url": "https://example.com/market"}
            ]

    research_client = FakeMarketResearchClient()
    state = complete_data().model_dump()
    state["consumer_research"] = {"summary": "Parents need simpler planning."}
    state["competitor_research"] = {
        "direct_competitors": [{"name": "Meal App"}]
    }
    report, sources = YouMCPMarketFeasibilityResearcher(research_client).research(state)

    assert "market signals and implementation feasibility" in research_client.question
    assert "Meal App" in research_client.question
    assert research_client.schema["additionalProperties"] is False
    assert set(research_client.schema["required"]) == set(
        research_client.schema["properties"]
    )
    assert report.demand_signals == [f"Signal {number}" for number in range(5)]
    assert sources == [
        {"title": "Market evidence", "url": "https://example.com/market"}
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
