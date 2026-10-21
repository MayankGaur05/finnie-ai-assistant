"""Descriptive portfolio-analysis node for user-provided holding weights."""

import json
from pathlib import Path

from src.core.llm_provider import get_llm_client
from src.core.settings import Settings
from src.core.state import CoreState


PROJECT_ROOT = Path(__file__).resolve().parents[2]
app_settings = Settings(PROJECT_ROOT / "config.yaml")
MODEL_NAME = app_settings.llm_provider_settings.model

PORTFOLIO_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
    },
    "required": ["response", "needs_clarification"],
}


class PortfolioAgentError(RuntimeError):
    """Raised when portfolio analysis cannot be generated or validated."""


def portfolio(state: CoreState) -> dict[str, object]:
    """Summarize user-supplied portfolio weights without recommending trades.

    The node does not look up holdings or infer their sectors, prices, or risk.
    It asks for allocation weights when the user has only supplied ticker names.
    """
    user_input = state["user_input"]
    prompt = f"""
You are Finnie, an educational personal finance assistant. Provide a neutral,
descriptive summary of portfolio information explicitly supplied by the user.

Use only the facts in the request. Do not look up or infer company names,
sectors, asset classes, prices, correlations, future returns, or risk from
symbols alone. Do not invent holding weights or assume that the listed holdings
are the user's entire portfolio.

To describe concentration, you need the holdings and their portfolio weights
(percentages are preferred). If weights are missing or unclear, ask the user
for the holding names and approximate percentage or market value of each, and
whether the list represents the full portfolio. Ask up to five focused
questions, then set needs_clarification to true. Do not ask for account numbers,
credentials, or other identifying details.

If the supplied data is sufficient, summarize only what the weights show.
Identify the largest positions and any stated allocation concentration. If the
weights do not total approximately 100%, flag that limitation instead of
silently normalizing them. Do not claim diversification based only on the
number of holdings. Do not recommend buying, selling, or changing allocations,
and do not provide individualized investment, tax, or legal advice.

Return a JSON object matching the response schema. The response field must
contain the complete user-facing answer. Set needs_clarification to true only
when asking for essential portfolio information.

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
                "schema": PORTFOLIO_RESPONSE_SCHEMA,
            },
        )
    except Exception as exc:
        raise PortfolioAgentError(
            "Gemini failed to generate the portfolio summary."
        ) from exc

    output_text = interaction.output_text
    if not isinstance(output_text, str) or not output_text.strip():
        raise PortfolioAgentError("Gemini returned an empty portfolio response.")

    try:
        result = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise PortfolioAgentError(
            "Gemini returned malformed JSON for the portfolio summary."
        ) from exc

    if not isinstance(result, dict):
        raise PortfolioAgentError("Gemini returned an invalid portfolio response.")

    response = result.get("response")
    needs_clarification = result.get("needs_clarification")
    if not isinstance(response, str) or not response.strip():
        raise PortfolioAgentError("Gemini returned no user-facing portfolio summary.")
    if not isinstance(needs_clarification, bool):
        raise PortfolioAgentError("Gemini returned an invalid clarification flag.")

    return {
        "response": response.strip(),
        "needs_clarification": needs_clarification,
        "retrieved_context": [],
        "sources": [],
        "tool_result": {"workflow": "portfolio", "data_source": "user-provided"},
        "error": "",
    }
