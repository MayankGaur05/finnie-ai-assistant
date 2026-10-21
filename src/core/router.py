from .state import CoreState, Intent


def route_intent(state: CoreState) -> Intent:
    """Return the graph branch for the intent already stored in the state.

    Request classification should happen before this dispatcher is called.
    Missing or invalid intent values safely route to clarification.
    """

    intent = state.get("intent")
    if intent in {
        "finance_qa",
        "portfolio",
        "market",
        "goals",
        "clarify",
        "out_of_scope",
    }:
        return intent

    return "clarify"
