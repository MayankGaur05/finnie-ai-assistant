"""Deterministic clarification node for ambiguous user requests."""

from src.core.state import CoreState


def clarify(state: CoreState) -> dict[str, object]:
    """Ask the user which Finnie workflow they want to use."""
    return {
        "response": (
            "What would you like help with? I can explain a general finance topic, "
            "describe holdings you provide, look up the latest available quote "
            "for one stock ticker, or help plan a savings or budgeting goal. "
            "Tell me which of those you mean."
        ),
        "needs_clarification": True,
        "retrieved_context": [],
        "sources": [],
        "tool_result": {"workflow": "clarify"},
        "error": "",
    }
