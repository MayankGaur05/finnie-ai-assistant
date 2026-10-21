"""Deterministic response node for unsupported requests."""

from src.core.state import CoreState


def out_of_scope(state: CoreState) -> dict[str, object]:
    """Set a clear boundary and point the user to supported Finnie features."""
    return {
        "response": (
            "I can't help with that request. Finnie can explain general finance "
            "topics, describe portfolio information you provide, look up the "
            "latest available quote for one stock ticker, and support general "
            "savings or budgeting goals. I can provide educational context, but "
            "not individualized buy or sell recommendations."
        ),
        "needs_clarification": False,
        "retrieved_context": [],
        "sources": [],
        "tool_result": {"workflow": "out_of_scope"},
        "error": "",
    }
