"""
src/prior_auth_copilot/graph.py

LangGraph StateGraph for the Prior-Auth Co-pilot.

Phase 4.3 shape:
    Intake (stub) ──► Evidence Gatherer ──► Reasoner ──► END

Later phases will extend:
    ... ──► PAS Bundle Builder (4.4)
        ──► Reviewer / HITL interrupt (4.4)
        ──► Submit (4.4)

Usage:
    from prior_auth_copilot.graph import build_graph

    graph = build_graph()
    result = graph.invoke({
        "patient_id": "abc-123",
        "service": ServiceRequest(service_code="241615005", service_display="MRI lumbar spine"),
    })
    print(result["decision"].overall_recommendation)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from prior_auth_copilot.nodes.evidence_gatherer import evidence_gatherer_node
from prior_auth_copilot.nodes.intake import intake_node
from prior_auth_copilot.nodes.reasoner import reasoner_node
from prior_auth_copilot.state import PAState


def _after_intake(state: PAState) -> str:
    """Conditional edge after Intake: abort on error."""
    return END if state.get("error") else "evidence_gatherer"


def _after_evidence(state: PAState) -> str:
    """Conditional edge after Evidence Gatherer: abort on error."""
    return END if state.get("error") else "reasoner"


def build_graph() -> StateGraph:
    """
    Build and compile the Phase 4.3 LangGraph.
    Returns a compiled graph ready to call with .invoke() or .stream().
    """
    graph = StateGraph(PAState)

    # ── Nodes ─────────────────────────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("evidence_gatherer", evidence_gatherer_node)
    graph.add_node("reasoner", reasoner_node)

    # ── Edges ──────────────────────────────────────────────────────────────
    graph.set_entry_point("intake")

    graph.add_conditional_edges(
        "intake",
        _after_intake,
        {"evidence_gatherer": "evidence_gatherer", END: END},
    )

    graph.add_conditional_edges(
        "evidence_gatherer",
        _after_evidence,
        {"reasoner": "reasoner", END: END},
    )

    graph.add_edge("reasoner", END)

    return graph.compile()


# Singleton graph — import and call directly in scripts / tests.
graph = build_graph()
