"""
src/prior_auth_copilot/graph.py

LangGraph StateGraph for the Prior-Auth Co-pilot.

Phase 4.4 shape:
    Intake ──► Evidence Gatherer ──► Reasoner ──► Bundle Builder
        ──► Validate Bundle ──► Reviewer (HITL interrupt) ──► Submit ──► END

    Reviewer branches:
      approve   → Submit → END
      edit      → Validate Bundle (re-validate with edited justification)
      send_back → Reasoner (replay with feedback)

SQLite checkpointer (ADR-0008): data/checkpoints/pa.db

Usage:
    from prior_auth_copilot.graph import build_graph, get_checkpointer

    with get_checkpointer() as saver:
        graph = build_graph(saver)
        config = {"configurable": {"thread_id": f"pa-{patient_id}"}}
        result = graph.invoke(initial_state, config=config)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

from prior_auth_copilot.nodes.bundle_builder import bundle_builder_node
from prior_auth_copilot.nodes.evidence_gatherer import evidence_gatherer_node
from prior_auth_copilot.nodes.intake import intake_node
from prior_auth_copilot.nodes.reasoner import reasoner_node
from prior_auth_copilot.nodes.reviewer import reviewer_node
from prior_auth_copilot.nodes.submit import submit_node
from prior_auth_copilot.nodes.validate_bundle import validate_bundle_node
from prior_auth_copilot.state import PAState

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CHECKPOINT_DB = _REPO_ROOT / os.getenv("CHECKPOINT_DB", "data/checkpoints/pa.db")


@contextmanager
def get_checkpointer():
    """Context manager providing the SQLite checkpointer (ADR-0008)."""
    _CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(_CHECKPOINT_DB)) as saver:
        yield saver


# ---------------------------------------------------------------------------
# Conditional edge routing
# ---------------------------------------------------------------------------


def _after_node(next_node: str):
    """Factory for standard error-short-circuit edges."""
    def _route(state: PAState) -> str:
        return END if state.get("error") else next_node
    return _route


def _after_reviewer(state: PAState) -> str:
    """Route based on the reviewer's action."""
    if state.get("error"):
        return END
    action = state.get("reviewer_action")
    if action is None:
        return END
    if action.action == "approve":
        return "submit"
    elif action.action == "edit":
        return "validate_bundle"  # re-validate with edited justification
    elif action.action == "send_back":
        return "reasoner"  # replay Reasoner with feedback
    return END


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(checkpointer=None) -> StateGraph:
    """
    Build and compile the Phase 4.4 LangGraph.

    Parameters
    ----------
    checkpointer : optional SqliteSaver (or any BaseCheckpointSaver).
                   If None, graph runs without persistence (no HITL interrupt).
    """
    graph = StateGraph(PAState)

    # ── Nodes ─────────────────────────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("evidence_gatherer", evidence_gatherer_node)
    graph.add_node("reasoner", reasoner_node)
    graph.add_node("bundle_builder", bundle_builder_node)
    graph.add_node("validate_bundle", validate_bundle_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("submit", submit_node)

    # ── Edges ──────────────────────────────────────────────────────────────
    graph.set_entry_point("intake")

    graph.add_conditional_edges("intake",          _after_node("evidence_gatherer"), {"evidence_gatherer": "evidence_gatherer", END: END})
    graph.add_conditional_edges("evidence_gatherer",_after_node("reasoner"),          {"reasoner": "reasoner", END: END})
    graph.add_conditional_edges("reasoner",         _after_node("bundle_builder"),    {"bundle_builder": "bundle_builder", END: END})
    graph.add_conditional_edges("bundle_builder",   _after_node("validate_bundle"),   {"validate_bundle": "validate_bundle", END: END})
    graph.add_conditional_edges("validate_bundle",  _after_node("reviewer"),          {"reviewer": "reviewer", END: END})

    # Reviewer branches: approve → submit | edit → re-validate | send_back → reasoner
    graph.add_conditional_edges(
        "reviewer",
        _after_reviewer,
        {"submit": "submit", "validate_bundle": "validate_bundle", "reasoner": "reasoner", END: END},
    )

    graph.add_edge("submit", END)

    return graph.compile(checkpointer=checkpointer, interrupt_before=["reviewer"] if checkpointer else [])


# Singleton for scripts that don't need HITL (no checkpointer, no interrupt).
graph = build_graph()
