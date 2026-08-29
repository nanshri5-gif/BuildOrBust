import html
import json
import os
import sqlite3
import uuid
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from langgraph.types import Command

from build_or_bust.dashboard import confidence_chart_data
from build_or_bust.graph import open_graph
from build_or_bust.idea_registry import SQLiteIdeaRegistry


def public_demo_mode() -> bool:
    return os.getenv("PUBLIC_DEMO_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def apply_app_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        :root {
            --paper: #F6F7F5;
            --panel: #FFFFFF;
            --ink: #1B2430;
            --ink-soft: #5B6673;
            --line: #D8DDE3;
            --blue: #2B5D8C;
            --blue-soft: #EAF1F7;
            --build: #1E7A4C;
            --bust: #B23A2E;
            --amber: #C77F1E;
        }
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'IBM Plex Sans', sans-serif;
            color: var(--ink);
        }
        .stApp, [data-testid="stAppViewContainer"] { background: var(--paper); }
        [data-testid="stHeader"] { background: rgba(246,247,245,.92); }
        [data-testid="stMainBlockContainer"] {
            max-width: 1380px;
            padding: 2.25rem 3rem 5rem;
        }
        h1, h2, h3, h4 {
            font-family: 'Space Grotesk', sans-serif !important;
            letter-spacing: -0.01em;
            color: var(--ink);
        }
        .app-eyebrow {
            font-family: 'IBM Plex Mono', monospace;
            color: var(--blue);
            font-size: .7rem;
            letter-spacing: .14em;
            text-transform: uppercase;
            margin-bottom: .55rem;
        }
        .app-title {
            font-family: 'Space Grotesk', sans-serif;
            color: var(--ink);
            font-size: 2.75rem;
            font-weight: 700;
            letter-spacing: -.01em;
            line-height: 1.05;
            margin: 0 0 .65rem;
        }
        .app-subtitle {
            color: var(--ink-soft);
            font-size: .98rem;
            margin-bottom: 2rem;
        }
        [data-testid="stSidebar"] {
            background: var(--panel);
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding: 1.7rem 1.1rem;
        }
        [data-testid="stSidebar"] h3 {
            font-family: 'IBM Plex Mono', monospace !important;
            color: var(--ink-soft);
            font-size: .7rem;
            letter-spacing: .1em;
            text-transform: uppercase;
        }
        [data-testid="stSidebar"] .stButton > button {
            background: var(--paper);
            border: 1px solid var(--line);
            border-left: 3px solid var(--build);
            border-radius: 2px;
            color: var(--ink);
            font-size: .78rem;
            line-height: 1.35;
            min-height: 3rem;
            text-align: left;
            justify-content: flex-start;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            border-color: var(--blue);
            color: var(--blue);
        }
        .idea-dossier {
            position: relative;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 2px;
            padding: 1.35rem 1.5rem;
            margin-bottom: .75rem;
            box-shadow: 0 1px 0 rgba(27,36,48,.05);
        }
        .idea-dossier, .idea-dossier * {
            font-family: Georgia, 'Times New Roman', serif !important;
        }
        .idea-dossier:before, .idea-dossier:after {
            content: '';
            position: absolute;
            width: 10px;
            height: 10px;
            border: 1.5px solid var(--blue);
            opacity: .55;
        }
        .idea-dossier:before {
            top: -1px; left: -1px; border-right: none; border-bottom: none;
        }
        .idea-dossier:after {
            right: -1px; bottom: -1px; border-left: none; border-top: none;
        }
        .dossier-label {
            font-family: 'IBM Plex Mono', monospace;
            color: var(--blue);
            font-size: .66rem;
            letter-spacing: .1em;
            text-transform: uppercase;
            margin-bottom: .6rem;
        }
        .dossier-text { color: var(--ink); font-size: 1rem; line-height: 1.55; }
        .product-brief {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1.7rem 1.9rem;
        }
        .brief-product {
            border-bottom: 1px solid var(--line);
            padding-bottom: 1.35rem;
            margin-bottom: 1.35rem;
        }
        .brief-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            column-gap: 3rem;
            row-gap: 1.4rem;
        }
        .brief-field {
            display: grid;
            grid-template-columns: 1.65rem 1fr;
            gap: .7rem;
            align-items: start;
        }
        .brief-icon {
            width: 1.35rem;
            height: 1.35rem;
            color: #8D8C87;
            margin-top: .1rem;
        }
        .brief-icon svg {
            width: 100%;
            height: 100%;
            fill: none;
            stroke: currentColor;
            stroke-width: 1.8;
            stroke-linecap: round;
            stroke-linejoin: round;
        }
        .brief-label {
            color: #8D8C87;
            font-size: .76rem;
            font-weight: 700;
            letter-spacing: .02em;
            text-transform: uppercase;
            margin-bottom: .25rem;
        }
        .brief-value {
            color: var(--ink);
            font-size: 1.05rem;
            line-height: 1.45;
        }
        .brief-product .brief-value { font-size: 1.2rem; }
        .ruling-panel {
            background: var(--panel);
            border: 1px solid var(--line);
            padding: 2rem 2.25rem 1.8rem;
            color: var(--ink);
        }
        .ruling-eyebrow, .confidence-labels {
            font-family: 'IBM Plex Mono', monospace;
            font-size: .7rem;
            letter-spacing: .13em;
            text-transform: uppercase;
        }
        .ruling-eyebrow { color: var(--ink-soft); margin-bottom: 1.6rem; }
        .ruling-heading { display: flex; align-items: center; gap: 1.4rem; }
        .ruling-stamp {
            width: 7rem;
            height: 7rem;
            border: 4px solid var(--ruling-color);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 7rem;
            color: var(--ruling-color);
            font-family: 'IBM Plex Mono', monospace;
            font-size: 1rem;
            font-weight: 700;
            transform: rotate(-7deg);
        }
        .ruling-word {
            color: var(--ruling-color);
            font-family: Georgia, 'Times New Roman', serif;
            font-size: clamp(3.4rem, 7vw, 5.5rem);
            font-weight: 700;
            letter-spacing: -.04em;
            line-height: .95;
        }
        .ruling-rationale {
            max-width: 62rem;
            margin: 1.8rem 0 2.25rem;
            color: var(--ink);
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 1.05rem;
            line-height: 1.65;
        }
        .ruling-rationale strong { color: var(--ruling-color); }
        .confidence-labels {
            display: flex;
            justify-content: space-between;
            color: var(--ink-soft);
            margin-bottom: .55rem;
        }
        .confidence-track {
            height: 1.35rem;
            border: 1px solid var(--ruling-color);
            background: var(--paper);
            overflow: hidden;
        }
        .confidence-fill {
            height: 100%;
            background-color: var(--ruling-color);
            background-image: repeating-linear-gradient(
                45deg,
                rgba(255,255,255,.1) 0,
                rgba(255,255,255,.1) 7px,
                rgba(0,0,0,.08) 7px,
                rgba(0,0,0,.08) 14px
            );
        }
        .readiness-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(150px, 1fr));
            gap: 1.5rem;
            align-items: start;
            padding: .75rem 0 1rem;
        }
        .readiness-gauge { text-align: center; }
        .readiness-gauge svg { width: 8.2rem; height: 8.2rem; }
        .readiness-track {
            fill: none;
            stroke: #E3E4E1;
            stroke-width: 11;
        }
        .readiness-value {
            fill: var(--ink);
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 1.4rem;
            font-weight: 700;
        }
        .readiness-label {
            color: var(--ink);
            font-family: Georgia, 'Times New Roman', serif;
            font-size: .95rem;
            font-weight: 600;
            line-height: 1.35;
            margin-top: .35rem;
        }
        .stButton > button, .stFormSubmitButton > button {
            font-family: 'IBM Plex Mono', monospace;
            border: 1px solid var(--line);
            border-radius: 2px;
            background: var(--panel);
            color: var(--ink-soft);
            font-size: .73rem;
            letter-spacing: .03em;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover {
            border-color: var(--blue);
            color: var(--blue);
        }
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {
            background: var(--ink);
            border-color: var(--ink);
            color: white;
        }
        .st-key-evaluate_another_idea button {
            background: var(--panel) !important;
            border: 1px solid var(--line) !important;
            color: var(--ink) !important;
            font-family: Georgia, 'Times New Roman', serif !important;
            font-size: .88rem;
            padding: .65rem 1rem;
        }
        .st-key-evaluate_another_idea button:hover {
            background: #FAFAF8 !important;
            border-color: var(--blue) !important;
            color: var(--blue) !important;
        }
        .review-summary {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: .9rem 0 .75rem;
        }
        .review-pill {
            display: inline-flex;
            align-items: center;
            gap: .55rem;
            border-radius: 10px;
            background: var(--review-background);
            color: var(--review-color);
            font-family: Georgia, 'Times New Roman', serif;
            font-size: .92rem;
            font-weight: 600;
            padding: .55rem .9rem;
        }
        .stTextArea textarea {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 2px;
            color: var(--ink);
        }
        .stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] {
            gap: 2px;
            border-bottom: 1px solid var(--line);
            overflow-x: auto;
        }
        .stTabs [data-baseweb="tab"], .stTabs [role="tab"] {
            font-family: 'IBM Plex Mono', monospace;
            color: var(--ink-soft) !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            border-bottom: none !important;
            border-radius: 4px 4px 0 0 !important;
            padding: .7rem 1rem;
            font-size: .72rem;
            letter-spacing: .02em;
        }
        .stTabs [role="tab"][aria-selected="true"] {
            color: var(--ink) !important;
            background: var(--panel) !important;
            border-color: var(--line) !important;
            font-weight: 600;
        }
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [role="tab"][aria-selected="true"] > div:last-child {
            background: transparent !important;
        }
        .stTabs [data-baseweb="tab-panel"], .stTabs [role="tabpanel"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-top: none;
            border-radius: 0 0 4px 4px;
            padding: 1.5rem;
        }
        .stTabs [role="tabpanel"],
        .stTabs [role="tabpanel"] * {
            font-family: Georgia, 'Times New Roman', serif !important;
        }
        .stTabs [role="tabpanel"] [data-testid="stIconMaterial"] {
            font-family: 'Material Symbols Rounded' !important;
        }
        .stTabs [role="tabpanel"] [data-testid="stExpander"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            margin-bottom: 1rem;
            overflow: hidden;
        }
        .stTabs [role="tabpanel"] [data-testid="stExpander"] summary {
            background: var(--panel) !important;
            color: var(--ink) !important;
            padding: .45rem .7rem;
            font-size: 1rem;
            font-weight: 600;
        }
        .stTabs [role="tabpanel"] [data-testid="stExpander"] summary:hover {
            background: #FAFAF8 !important;
            color: var(--ink) !important;
        }
        .recommendation-purpose {
            color: var(--ink-soft);
            font-size: 1rem;
            line-height: 1.55;
            margin-bottom: 1rem;
        }
        .recommendation-action {
            color: var(--ink);
            font-size: 1rem;
            line-height: 1.55;
            margin-bottom: 1rem;
            white-space: normal;
        }
        .completion-target {
            background: #FAFAF8;
            border-radius: 12px;
            color: var(--ink-soft);
            line-height: 1.55;
            padding: 1rem 1.1rem;
        }
        .completion-target strong { color: var(--ink); }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--line) !important;
            border-radius: 2px !important;
            background: var(--panel);
        }
        [data-testid="stAlert"] { border-radius: 2px; }
        hr { border-color: var(--line); }
        @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"] { padding: 1.5rem 1rem 4rem; }
            .app-title { font-size: 2.1rem; }
            .ruling-panel { padding: 1.4rem; }
            .ruling-heading { align-items: flex-start; gap: 1rem; }
            .ruling-stamp { width: 5rem; height: 5rem; flex-basis: 5rem; font-size: .78rem; }
            .ruling-word { font-size: 2.8rem; }
            .readiness-grid { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
        }
        @media (max-width: 520px) {
            .readiness-grid { grid-template-columns: 1fr; }
            .brief-grid { grid-template-columns: 1fr; }
            .product-brief { padding: 1.25rem; }
            .review-summary { align-items: flex-start; flex-direction: column; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_graph(request: dict[str, Any] | Command, thread_id: str) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    with open_graph(
        os.getenv("CHECKPOINT_DB", "build_or_bust.db"),
        enable_idea_registry=not public_demo_mode(),
    ) as graph:
        return graph.invoke(request, config=config)


def checkpoint_result(snapshot: Any) -> dict[str, Any]:
    result = dict(snapshot.values)
    interrupts = [
        item
        for task in getattr(snapshot, "tasks", ())
        for item in getattr(task, "interrupts", ())
    ]
    if interrupts:
        result["__interrupt__"] = tuple(interrupts)
    return result


def load_checkpoint(thread_id: str) -> dict[str, Any] | None:
    config = {"configurable": {"thread_id": thread_id}}
    with open_graph(
        os.getenv("CHECKPOINT_DB", "build_or_bust.db"),
        enable_idea_registry=not public_demo_mode(),
    ) as graph:
        snapshot = graph.get_state(config)
    if not snapshot.values:
        return None
    return checkpoint_result(snapshot)


def resume(action: str, notes: str = "") -> None:
    with st.spinner("Resuming the saved evaluation…"):
        st.session_state.result = run_graph(
            Command(resume={"action": action, "notes": notes}),
            st.session_state.thread_id,
        )


def load_history() -> list[dict[str, Any]]:
    db_path = os.getenv("CHECKPOINT_DB", "build_or_bust.db")
    SQLiteIdeaRegistry(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT evaluation_id, created_at, decision, confidence, review_action,
                   intake_json, snapshot_json
            FROM idea_evaluations
            WHERE review_action IN ('approve', 'reject')
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
    return [
        {
            "evaluation_id": row["evaluation_id"],
            "created_at": row["created_at"],
            "decision": row["decision"],
            "confidence": row["confidence"],
            "review_action": row["review_action"],
            "intake": json.loads(row["intake_json"]),
            "snapshot": json.loads(row["snapshot_json"]),
        }
        for row in rows
    ]


def show_sources(sources: list[dict[str, Any]]) -> None:
    for source in sources:
        title = source.get("title") or source.get("url") or "Source"
        url = source.get("url")
        if url:
            st.markdown(f"- [{title}]({url})")


def show_research(report: dict[str, Any], sources: list[dict]) -> None:
    if report.get("summary"):
        with st.expander("Summary", expanded=False):
            st.write(report["summary"])
    for key, value in report.items():
        if key == "summary" or not value:
            continue
        with st.expander(key.replace("_", " ").title(), expanded=False):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        with st.container(border=True):
                            st.markdown(f"#### {item.get('name', 'Finding')}")
                            for field, detail in item.items():
                                if field == "name" or detail in (None, "", []):
                                    continue
                                label = field.replace("_", " ").title()
                                st.markdown(f"**{label}**")
                                if isinstance(detail, list):
                                    for entry in detail:
                                        st.markdown(f"- {entry}")
                                else:
                                    st.write(detail)
                    else:
                        st.markdown(f"- {item}")
            else:
                st.write(value)
    if sources:
        with st.expander("Sources", expanded=False):
            show_sources(sources)


def recommendation_label(number: int, action: str, max_chars: int = 88) -> str:
    """Return a compact expander label without triggering Markdown math."""

    title = " ".join(str(action).split())
    first_sentence = title.split(". ", 1)[0]
    if len(first_sentence) > max_chars:
        shortened = first_sentence[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:-")
        first_sentence = f"{shortened or first_sentence[:max_chars]}…"
    escaped = (
        first_sentence.replace("\\", "\\\\")
        .replace("$", "\\$")
        .replace("_", "\\_")
        .replace("*", "\\*")
    )
    return f"{number}. {escaped} · Not started"


def recommendation_action_html(action: str) -> str:
    """Render model-generated action text literally instead of as Markdown."""

    return f"<div class='recommendation-action'>{html.escape(str(action))}</div>"


def show_recommendation(recommendation: dict[str, Any]) -> None:
    for number, action in enumerate(recommendation["next_actions"], start=1):
        full_action = str(action["action"])
        label = recommendation_label(number, full_action)
        with st.expander(label, expanded=False):
            st.markdown(
                recommendation_action_html(full_action), unsafe_allow_html=True
            )
            purpose = html.escape(str(action["purpose"]))
            completion = html.escape(str(action["completion_criterion"]))
            st.markdown(
                f"<div class='recommendation-purpose'>{purpose}</div>"
                "<div class='completion-target'>◎ &nbsp;<strong>Complete when:</strong> "
                f"{completion}</div>",
                unsafe_allow_html=True,
            )
    with st.expander("Build now", expanded=False):
        for item in recommendation["build_now"]:
            st.markdown(f"- {item}")
    with st.expander("Do not build yet", expanded=False):
        for item in recommendation["do_not_build_yet"]:
            st.markdown(f"- {item}")


def show_validation_experiments(experiments: list[dict[str, Any]]) -> None:
    for number, experiment in enumerate(experiments, start=1):
        with st.expander(f"Experiment {number}", expanded=False):
            st.markdown(f"**Hypothesis:** {experiment['hypothesis']}")
            st.write(experiment["method"])
            st.markdown(f"- **Success:** {experiment['success_criterion']}")
            st.markdown(f"- **Failure:** {experiment['failure_signal']}")


def show_confidence_gauges(chart_data: list[dict[str, float | str]]) -> None:
    scores = {str(item["Measure"]): float(item["Percent"]) for item in chart_data}
    order = [
        "Market evidence readiness",
        "Competitor evidence readiness",
        "Consumer evidence readiness",
        "Judge confidence",
    ]
    circumference = 314.159
    gauges = []
    for label in order:
        if label not in scores:
            continue
        percent = max(0.0, min(100.0, scores[label]))
        offset = circumference * (1 - percent / 100)
        if percent >= 100:
            color = "#15803d"
        else:
            color = "#2F7DDB" if label == "Judge confidence" else "#8D8C87"
        gauges.append(
            f"<div class='readiness-gauge'>"
            f"<svg viewBox='0 0 120 120' role='img' "
            f"aria-label='{html.escape(label)} {percent:.0f} percent'>"
            "<circle class='readiness-track' cx='60' cy='60' r='50'></circle>"
            f"<circle cx='60' cy='60' r='50' fill='none' stroke='{color}' "
            f"stroke-width='11' stroke-linecap='round' stroke-dasharray='{circumference}' "
            f"stroke-dashoffset='{offset:.3f}' transform='rotate(-90 60 60)'></circle>"
            f"<text class='readiness-value' x='60' y='67' text-anchor='middle'>"
            f"{percent:.0f}%</text></svg>"
            f"<div class='readiness-label'>{html.escape(label)}</div></div>"
        )
    st.markdown(
        f"<div class='readiness-grid'>{''.join(gauges)}</div>",
        unsafe_allow_html=True,
    )


def show_normalized_product(normalized: dict[str, Any]) -> None:
    icons = {
        "Product": "<path d='M12 3 4 7v10l8 4 8-4V7l-8-4Z M4 7l8 4 8-4 M12 11v10'/>",
        "Customer": "<circle cx='9' cy='8' r='3'/><path d='M3 20v-2a6 6 0 0 1 12 0v2 M16 5a3 3 0 0 1 0 6 M18 14a5 5 0 0 1 3 4v2'/>",
        "Geography": "<path d='M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z'/><circle cx='12' cy='10' r='2.5'/>",
        "Problem": "<path d='M10.3 3.7 2.4 18a2 2 0 0 0 1.8 3h15.6a2 2 0 0 0 1.8-3L13.7 3.7a2 2 0 0 0-3.4 0Z M12 9v4 M12 17h.01'/>",
        "Product type": "<rect x='4' y='4' width='6' height='6'/><rect x='14' y='4' width='6' height='6'/><rect x='4' y='14' width='6' height='6'/><rect x='14' y='14' width='6' height='6'/>",
    }

    def field(label: str) -> str:
        value = html.escape(str(normalized.get(label) or "Missing"))
        return (
            "<div class='brief-field'>"
            f"<div class='brief-icon'><svg viewBox='0 0 24 24'>{icons[label]}</svg></div>"
            "<div>"
            f"<div class='brief-label'>{html.escape(label)}</div>"
            f"<div class='brief-value'>{value}</div>"
            "</div></div>"
        )

    st.markdown(
        "<div class='product-brief'>"
        f"<div class='brief-product'>{field('Product')}</div>"
        "<div class='brief-grid'>"
        f"{field('Customer')}{field('Geography')}"
        f"{field('Problem')}{field('Product type')}"
        "</div></div>",
        unsafe_allow_html=True,
    )


def show_idea_overview(result: dict[str, Any]) -> None:
    proposal = result.get("raw_input") or result.get("product_idea")
    st.subheader("Idea overview")
    proposal_text = html.escape(str(proposal or "Idea proposal unavailable."))
    st.markdown(
        "<div class='idea-dossier'>"
        "<div class='dossier-label'>Idea proposal</div>"
        f"<div class='dossier-text'>{proposal_text}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def show_review_summary(result: dict[str, Any]) -> None:
    action = str(result.get("review_action") or "complete").lower()
    action_label = {"approve": "approved", "reject": "rejected"}.get(
        action, action
    )
    review_color, review_background = {
        "approve": ("#0f6b2b", "#d9f2d8"),
        "reject": ("#991b1b", "#fee2e2"),
    }.get(action, ("#475569", "#f1f5f9"))
    st.markdown(
        "<div class='review-summary'>"
        f"<div class='review-pill' style='--review-color:{review_color};"
        f"--review-background:{review_background};'>"
        f"<span>✓</span><span>Human review complete: {html.escape(action_label)}</span>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    if result.get("review_notes"):
        st.caption(result["review_notes"])


def result_tabs_config(
    result: dict[str, Any], tab_names: list[str]
) -> tuple[str, str]:
    """Return a fresh tab identity when clarification becomes a final result."""

    default_tab = "Decision" if "Decision" in tab_names else tab_names[0]
    phase = "decision" if default_tab == "Decision" else "clarification"
    thread_id = str(result.get("thread_id") or "current")
    return default_tab, f"result_tabs_{thread_id}_{phase}"


def result_tabs_visible(result: dict[str, Any]) -> bool:
    """Keep partial intake data out of result tabs during clarification."""

    return result.get("status") != "needs_clarification"


def show_results(result: dict[str, Any]) -> None:
    if result.get("status") == "error":
        st.error(f"{result.get('error_code')}: {result.get('error_message')}")
        return
    if result.get("status") == "insufficient_information":
        st.warning(result.get("error_message"))
        return
    if not result_tabs_visible(result):
        return
    if result.get("status") == "insufficient_evidence":
        st.warning("Research stopped because the deterministic evidence gate did not pass.")
        for check in result["evidence_assessment"]["failed_checks"]:
            st.markdown(f"- {check}")

    judgment = result.get("judgment")
    recommendation = result.get("recommendation")
    normalized = {
        "Product": result.get("product_idea"),
        "Customer": result.get("target_customer"),
        "Geography": result.get("geography"),
        "Problem": result.get("problem"),
        "Product type": result.get("product_type"),
    }

    research_tabs = []
    if judgment:
        research_tabs.append("Decision")
    if judgment and judgment.get("decision_criteria"):
        research_tabs.append("Decision criteria")
    if recommendation:
        research_tabs.append("Recommendation")
    if recommendation and recommendation.get("validation_experiments"):
        research_tabs.append("Validation experiments")
    if any(normalized.values()):
        research_tabs.append("Normalized product idea")
    chart_data = confidence_chart_data(result)
    if chart_data:
        research_tabs.append("Confidence & readiness")
    if result.get("consumer_research"):
        research_tabs.append("Consumer research")
    if result.get("competitor_research"):
        research_tabs.append("Competitor research")
    if result.get("market_feasibility_research"):
        research_tabs.append("Market & feasibility")
    if research_tabs:
        default_tab, tabs_key = result_tabs_config(result, research_tabs)
        tabs = dict(
            zip(
                research_tabs,
                st.tabs(research_tabs, default=default_tab, key=tabs_key),
            )
        )
        if "Decision" in tabs:
            with tabs["Decision"]:
                decision = judgment["decision"]
                decision_color = {
                    "BUILD": "#15803d",
                    "BUST": "#b91c1c",
                    "VALIDATE": "#a16207",
                    "PIVOT": "#a16207",
                }.get(decision, "#475569")
                confidence = max(0.0, min(1.0, float(judgment["confidence"])))
                reasoning = str(judgment["reasoning"]).strip()
                lead, separator, remainder = reasoning.partition(". ")
                lead_text = html.escape(lead + ("." if separator else ""))
                remainder_text = html.escape(remainder)
                rationale = f"<strong>{lead_text}</strong>"
                if remainder_text:
                    rationale += f" {remainder_text}"
                st.markdown(
                    f"<div class='ruling-panel' style='--ruling-color:{decision_color};'>"
                    "<div class='ruling-eyebrow'>Judge's ruling</div>"
                    "<div class='ruling-heading'>"
                    f"<div class='ruling-stamp'>{html.escape(decision)}</div>"
                    f"<div class='ruling-word'>{html.escape(decision)}</div>"
                    "</div>"
                    f"<div class='ruling-rationale'>{rationale}</div>"
                    "<div class='confidence-labels'><span>Confidence</span>"
                    f"<span>{confidence:.0%}</span></div>"
                    "<div class='confidence-track'>"
                    f"<div class='confidence-fill' style='width:{confidence:.1%};'></div>"
                    "</div></div>",
                    unsafe_allow_html=True,
                )
        if "Decision criteria" in tabs:
            with tabs["Decision criteria"]:
                for criterion in judgment["decision_criteria"]:
                    status = criterion["status"].lower()
                    color, background = {
                        "supported": ("#15803d", "#f0fdf4"),
                        "unsupported": ("#b91c1c", "#fef2f2"),
                        "unknown": ("#a16207", "#fffbeb"),
                    }.get(status, ("#475569", "#f8fafc"))
                    title = html.escape(str(criterion["criterion"]))
                    evidence = html.escape(str(criterion["evidence"]))
                    status_label = status.replace("_", " ").upper()
                    with st.expander(f"{title} — {status_label}", expanded=False):
                        st.markdown(
                            f"<div style='border-left:6px solid {color};"
                            f"border-radius:8px;background:{background};padding:1rem;'>"
                            f"<div style='color:#1f2937;'>{evidence}</div></div>",
                            unsafe_allow_html=True,
                        )
        if "Recommendation" in tabs:
            with tabs["Recommendation"]:
                show_recommendation(recommendation)
        if "Validation experiments" in tabs:
            with tabs["Validation experiments"]:
                show_validation_experiments(
                    recommendation["validation_experiments"]
                )
        if "Normalized product idea" in tabs:
            with tabs["Normalized product idea"]:
                show_normalized_product(normalized)
        if "Confidence & readiness" in tabs:
            with tabs["Confidence & readiness"]:
                show_confidence_gauges(chart_data)
                st.caption(
                    "Evidence readiness is deterministic and uses the weakest of "
                    "source count, domain diversity, required coverage, and competitor "
                    "extraction. Judge confidence is the model's separately reported "
                    "confidence."
                )
        if "Consumer research" in tabs:
            with tabs["Consumer research"]:
                show_research(
                    result["consumer_research"], result.get("research_sources", [])
                )
        if "Competitor research" in tabs:
            with tabs["Competitor research"]:
                show_research(
                    result["competitor_research"],
                    result.get("competitor_sources", []),
                )
        if "Market & feasibility" in tabs:
            with tabs["Market & feasibility"]:
                show_research(
                    result["market_feasibility_research"],
                    result.get("market_feasibility_sources", []),
                )

    if result.get("status") == "evaluation_reused":
        st.info(
            "Prior evaluation reused without new research calls. Evaluation ID: "
            f"{result.get('reused_from_evaluation_id')}"
        )
def show_interrupt(result: dict[str, Any]) -> None:
    if not result.get("__interrupt__"):
        return
    prompt = result["__interrupt__"][0].value
    st.divider()
    st.subheader(prompt["question"])
    kind = prompt.get("kind")
    if kind == "prior_evaluation":
        st.info(
            f"Previous decision: {prompt.get('decision')} · "
            f"Review: {prompt.get('review_action')} · Created: {prompt.get('created_at')}"
        )
        left, right = st.columns(2)
        if left.button("Reuse saved evaluation", type="primary", use_container_width=True):
            resume("reuse")
            st.rerun()
        if right.button("Refresh all research", use_container_width=True):
            resume("refresh")
            st.rerun()
    elif kind == "human_review":
        with st.form("human_review"):
            action = st.radio("Decision", ["approve", "reject"], horizontal=True)
            notes = st.text_area(
                "Notes",
                placeholder="Optional notes for the evaluation record.",
            )
            if st.form_submit_button("Submit review", type="primary"):
                resume(action, notes)
                st.rerun()
    else:
        with st.form("clarification"):
            answer = st.text_area("Your clarification")
            if st.form_submit_button("Continue", type="primary"):
                if not answer.strip():
                    st.error("Clarification cannot be empty.")
                else:
                    with st.spinner("Continuing the evaluation…"):
                        st.session_state.result = run_graph(
                            Command(resume=answer.strip()), st.session_state.thread_id
                        )
                    st.rerun()


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Build or Bust", page_icon="🔎", layout="wide")
    apply_app_style()
    if public_demo_mode():
        st.markdown(
            "<style>[data-testid='stSidebar']{display:none !important;}</style>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<div class='app-title'>Build or Bust</div>"
        "<div class='app-subtitle'>Turn a product idea into an evidence-backed "
        "decision and validation plan.</div>",
        unsafe_allow_html=True,
    )

    requested_thread = str(st.query_params.get("thread") or "").strip()
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = requested_thread or str(uuid.uuid4())
    if "result" not in st.session_state:
        st.session_state.result = None
    if requested_thread and st.session_state.get("loaded_thread") != requested_thread:
        restored = load_checkpoint(requested_thread)
        st.session_state.thread_id = requested_thread
        st.session_state.loaded_thread = requested_thread
        if restored is None:
            st.warning("No saved checkpoint exists for this thread ID.")
        else:
            st.session_state.result = restored
            st.success("Saved checkpoint restored. No research APIs were called.")

    with st.sidebar:
        st.subheader("Evaluation history")
        try:
            history = load_history()
        except (sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
            st.error(f"Could not load evaluation history: {exc}")
            history = []
        if not history:
            st.caption("Approved and rejected evaluations will appear here.")
        for evaluation in history:
            product = evaluation["intake"].get("product_idea") or "Untitled idea"
            created = evaluation["created_at"][:10]
            decision = evaluation["decision"]
            confidence = evaluation.get("confidence")
            confidence_label = (
                f"{confidence:.0%} confidence"
                if confidence is not None
                else "Confidence unavailable"
            )
            if decision == "BUILD":
                st.markdown(
                    "<span style='color:#15803d;font-weight:700;'>BUILD</span>"
                    f" · <strong>{confidence_label}</strong>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"**{decision}** · **{confidence_label}**")
            if st.button(
                product,
                key=f"history-{evaluation['evaluation_id']}",
                help=f"{evaluation['review_action'].title()} on {created}",
                use_container_width=True,
            ):
                st.session_state.result = {
                    **evaluation["intake"],
                    **evaluation["snapshot"],
                    "status": "evaluation_reused",
                    "reused_from_evaluation_id": evaluation["evaluation_id"],
                }
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.loaded_thread = None
                st.query_params.clear()
                st.rerun()

    result = st.session_state.result
    if result:
        show_idea_overview(result)
        if result.get("status") == "review_complete":
            show_review_summary(result)
        if st.button(
            "↻  Evaluate another idea",
            type="secondary",
            key="evaluate_another_idea",
        ):
            st.session_state.result = None
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.loaded_thread = None
            st.query_params.clear()
            st.rerun()
    else:
        with st.form("product_idea"):
            idea = st.text_area(
                "What product are you considering?",
                placeholder=(
                    "Example: A portable, lightweight umbrella for children worldwide "
                    "that is easy to carry and handle."
                ),
                height=120,
            )
            submitted = st.form_submit_button("Evaluate idea", type="primary")
        if submitted:
            if not idea.strip():
                st.error("Please enter a product idea.")
            else:
                st.session_state.thread_id = str(uuid.uuid4())
                with st.spinner("Researching and evaluating the idea…"):
                    st.session_state.result = run_graph(
                        {
                            "raw_input": idea.strip(),
                            "status": "pending",
                            "thread_id": st.session_state.thread_id,
                        },
                        st.session_state.thread_id,
                    )
                st.session_state.loaded_thread = st.session_state.thread_id
                st.query_params["thread"] = st.session_state.thread_id
                st.rerun()

    result = st.session_state.result
    if result:
        show_results(result)
        show_interrupt(result)


if __name__ == "__main__":
    main()
