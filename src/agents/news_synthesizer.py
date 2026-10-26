import json
from pathlib import Path

from src.core.llm_provider import get_llm_client
from src.core.settings import Settings
from src.core.state import CoreState

PROJECT_ROOT = Path(__file__).resolve().parents[2]
app_settings = Settings(PROJECT_ROOT / "config.yaml")
MODEL_NAME = app_settings.llm_provider_settings.model

NewsSynthesizerSchema = {
    "heading": {"type": "string"},
    "summary": {"type": "string"},
    "date": {"type": "string"},
    "source": {"type": "string"},
    "key_points": {"type": "array", "items": {"type": "string"}},
    "further_references": {"type": "array", "items": {"type": "string"}}
}

NewsSynthesizerResponseSchema = {
    "type": "object",
   
    
    
    "properties": {
        "response": {"type": "object", "properties": NewsSynthesizerSchema},
        "needs_clarification": {"type": "boolean"}
    },
    "required": ["response", "needs_clarification"]
}

class NewsSynthesizerError(RuntimeError):
    """Exception raised for errors in the news synthesizer."""

def news_synthesizer(state: CoreState) -> dict[str, object]:
    user_input = state["user_input"]
    prompt = f"""You are Finnie, an educational personal finance assistant. You help synthesize financial news based on the user's input. User will provide a financial news article or information related to personal finance e.g.  explain the recent monetory poilcy changes issued by the RBI. Your task is to extract the headline, generate the summary in easy-to-understand language, extract the key points and present in bullet points, and provide further references if available. 
    You will search for past seven days of news related to the topic provided by the user and maximum of five relevant articles.
    Extract the following information from each relevant article:
    1. Heading
    2. Summary
    3. Date
    4. Source
    5. Key Points
    6. Further References (if available)
    7. Needs Clarification (boolean)
    Format the extracted information as a JSON object following the NewsSynthesizerSchema.
    Ensure that the JSON object is valid and contains all required fields.
    If any required information is missing, indicate it clearly in the JSON object.
    Respond only with the JSON object and nothing else.
    User Input: {user_input}

    """
    try:
        interaction = get_llm_client().interactions.create(
        model= MODEL_NAME,
        input=prompt,
        response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": NewsSynthesizerResponseSchema,
                },
            )
    except Exception as exc:
        raise NewsSynthesizerError("Gemini failed to generate news synthesis.") from exc
    
    output_text = interaction.output_text
    if not isinstance(output_text, str) or not output_text.strip():
        raise NewsSynthesizerError("Gemini returned an empty news synthesis response.")
    
    try:
        result = json.loads(output_text)
        print(result)
    except json.JSONDecodeError as exc:
        raise NewsSynthesizerError(
                "Gemini returned malformed JSON for news synthesis."
            ) from exc
    
    if not isinstance(result, dict):
        raise NewsSynthesizerError("Gemini returned an invalid news synthesis response.")
    
    response = result.get("response")
    needs_clarification = result.get("needs_clarification")
    if not isinstance(response, dict) or not response:
        raise NewsSynthesizerError("Gemini returned no user-facing news synthesis answer.")
    if not isinstance(needs_clarification, bool):
        raise NewsSynthesizerError("Gemini returned an invalid clarification flag.")

    return {
        "response": response,
        "needs_clarification": needs_clarification
    }

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "Recent T20 cricket world cup news for team India?"
    print(json.dumps(news_synthesizer({"user_input": query}), indent=2))