from typing import Literal, NotRequired, Required, TypedDict


Intent = Literal["finance_qa", "portfolio", "market", "goals", "clarify", "out_of_scope"]


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


class CoreState(TypedDict, total=False):
    """Shared state passed between Finnie's LangGraph workflow nodes.

    Nodes populate fields as the request moves through the graph. The original
    user request is the only field required when starting a workflow.
    """

    user_input: Required[str]
    intent: NotRequired[Intent]
    entities: NotRequired[dict[str, object]]
    retrieved_context: NotRequired[list[RetrievedChunk]]
    sources: NotRequired[list[SourceCitation]]
    tool_result: NotRequired[dict[str, object]]
    needs_clarification: NotRequired[bool]
    response: NotRequired[str]
    error: NotRequired[str]
