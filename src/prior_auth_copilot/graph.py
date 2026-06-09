"""
src/prior_auth_copilot/graph.py

LangGraph StateGraph for the Prior-Auth Co-pilot.

Phase 4.2 shape:
    Intake (stub) ──► Evidence Gatherer ──► END

Later phases will extend:
    ... ──► Medical Necessity Reasoner (4.3)
        ──► PAS Bundle Builder (4.4)
        ──► Reviewer / HITL interrupt (4.4)
        ──► Submit (4.4)

Usage:
    from prior_auth_copilot.graph import build_graph

    graph = build_graph()
    result = graph.invoke({
        "patient_id": "abc-123",
        "service": ServiceRequest(service_code="241615005", service_display="MRI lumbar spine"),
    })
    print(result["evidence_package"].gatherer_notes)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from prior_auth_copilot.nodes.evidence_gatherer import evidence_gatherer_node
from prior_auth_copilot.nodes.intake import intake_node
from prior_auth_copilot.state import PAState


def _should_continue(state: PAState) -> str:
    """Conditional edge: abort to END if any node set an error."""
    if state.get("error"):
        return END
    return "evidence_gatherer"


def build_graph() -> StateGraph:
    """
    Build and compile the Phase 4.2 LangGraph.

    Returns a compiled graph ready to call with .invoke() or .stream().
    """
    graph = StateGraph(PAState)

    # ── Nodes ────────────────────────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("evidence_gatherer", evidence_gatherer_node)

    # ── Edges ─────────────────────────────────────────────────────────────
    graph.set_entry_point("intake")

    # After Intake: proceed to Evidence Gatherer, or short-circuit on error.
    graph.add_conditional_edges(
        "intake",
        _should_continue,
        {
            "evidence_gatherer": "evidence_gatherer",
            END: END,
        },
    )

    graph.add_edge("evidence_gatherer", END)

    return graph.compile()


# Singleton graph — import and call directly in scripts / tests.
graph = build_graph()
