from typing import Literal, NotRequired, Required, TypedDict

Intent = Literal[
    "finance_qa",
    "portfolio",
    "market",
    "goals",
    "news",
    "clarify",
    "out_of_scope",
]
RequestedIntent = Literal["finance_qa", "portfolio", "market", "goals", "news"]


class RetrievedChunk(TypedDict):
    """One retrieved passage and its Chroma metadata."""

    text: str
    metadata: dict[str, str | int | float | bool]
    distance: float


class SourceCitation(TypedDict):
    """An article-level source, deduplicated across retrieved chunks."""

    title: str
    url: str
    distance: float


class NewsCitation(TypedDict):
    """Publisher attribution and publication time for a retrieved news article."""

    title: str
    url: str
    publisher: str
    published_at: str


class CoreState(TypedDict, total=False):
    """Shared state passed between Finnie's LangGraph workflow nodes.

    Nodes populate fields as the request moves through the graph. The original
    user request is the only field required when starting a workflow.
    """

    user_input: Required[str]
    intent: NotRequired[Intent]
    requested_intent: NotRequired[RequestedIntent]
    entities: NotRequired[dict[str, object]]
    retrieved_context: NotRequired[list[RetrievedChunk]]
    sources: NotRequired[list[SourceCitation | NewsCitation]]
    tool_result: NotRequired[dict[str, object]]
    needs_clarification: NotRequired[bool]
    response: NotRequired[str]
    error: NotRequired[str]
    portfolio_attachment_name: NotRequired[str]
    portfolio_attachment_text: NotRequired[str]
    portfolio_image_data: NotRequired[str]
    portfolio_image_mime_type: NotRequired[Literal["image/png", "image/jpeg"]]
