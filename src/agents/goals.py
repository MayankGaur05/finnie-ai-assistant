"""Goal-planning node for general savings and budgeting guidance."""

import json
from pathlib import Path

from src.core.llm_provider import get_llm_client
from src.core.settings import Settings
from src.core.state import CoreState


PROJECT_ROOT = Path(__file__).resolve().parents[2]
app_settings = Settings(PROJECT_ROOT / "config.yaml")
MODEL_NAME = app_settings.llm_provider_settings.model

GOALS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
    },
    "required": ["response", "needs_clarification"],
}


class GoalsAgentError(RuntimeError):
    """Raised when goal guidance cannot be generated or validated."""


def goals(state: CoreState) -> dict[str, object]:
    """Provide general goal-planning guidance or ask for missing details.

    This function returns a partial state update for use as a LangGraph node.
    It does not create an investment, tax, debt, or legal recommendation.
    """
    user_input = state["user_input"]
    prompt = f"""
You are Finnie, an educational personal finance assistant helping with savings,
budgeting, and financial goals. Use only details stated in the user's request.

If information needed for a useful goal plan is missing, ask up to five short,
focused questions and set needs_clarification to true. Depending on the goal,
useful details may include the target amount, deadline, current savings, current age, any ongoing 
EMIs or fixed monthly expenses, or an affordable contribution amount. Do not assume any of these values.

If enough detail is available, provide a practical, general savings plan. Show
any arithmetic and assumptions clearly. Do not promise an outcome or recommend
specific financial products, securities, or buy/sell actions. Do not provide
individualized tax, legal, debt, or investment advice. If the user requests
those, explain the limit and offer general educational information instead.

Return a JSON object matching the response schema. The response field must
contain the complete user-facing answer. Set needs_clarification to true only
when you are asking the user for information before making a plan.

User request:
<request>
{user_input}
</request>
"""

    try:
        interaction = get_llm_client().interactions.create(
            model=MODEL_NAME,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": GOALS_RESPONSE_SCHEMA,
            },
        )
    except Exception as exc:
        raise GoalsAgentError("Gemini failed to generate goal-planning guidance.") from exc

    output_text = interaction.output_text
    if not isinstance(output_text, str) or not output_text.strip():
        raise GoalsAgentError("Gemini returned an empty goal-planning response.")

    try:
        result = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise GoalsAgentError(
            "Gemini returned malformed JSON for goal-planning guidance."
        ) from exc

    if not isinstance(result, dict):
        raise GoalsAgentError("Gemini returned an invalid goal-planning response.")

    response = result.get("response")
    needs_clarification = result.get("needs_clarification")
    if not isinstance(response, str) or not response.strip():
        raise GoalsAgentError("Gemini returned no user-facing goal-planning answer.")
    if not isinstance(needs_clarification, bool):
        raise GoalsAgentError("Gemini returned an invalid clarification flag.")

    return {
        "response": response.strip(),
        "needs_clarification": needs_clarification,
        "error": "",
    }
