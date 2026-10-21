"""Finance education Q&A node backed by Finnie's Chroma knowledge base."""

from functools import lru_cache
from pathlib import Path

import chromadb

from src.core.llm_provider import get_llm_client
from src.core.settings import Settings
from src.core.state import CoreState, RetrievedChunk, SourceCitation


PROJECT_ROOT = Path(__file__).resolve().parents[2]

app_settings = Settings(PROJECT_ROOT / "config.yaml")
llm_settings = app_settings.llm_provider_settings
retriever_settings = app_settings.retriever_settings

# Keep this aligned with the cutoff evaluated for the current RAG workflow.
DISTANCE_THRESHOLD = 1.00


class FinanceQAError(RuntimeError):
    """Raised when retrieval or answer generation fails."""


@lru_cache(maxsize=1)
def get_collection():
    """Get the configured persistent Chroma collection once per process."""
    client = chromadb.PersistentClient(path=str(app_settings.db_directory_path))
    try:
        return client.get_collection(name=retriever_settings.collection_name)
    except Exception as exc:
        raise FinanceQAError(
            "The configured Finance Q&A knowledge base is unavailable."
        ) from exc


def finance_qa(state: CoreState) -> dict[str, object]:
    """Retrieve supporting passages and answer a finance education question.

    Returns only state updates so this function can be added as a LangGraph
    node. It does not print or execute test queries at import time.
    """
    question = state["user_input"]

    try:
        collection = get_collection()
        available_count = collection.count()
        if available_count == 0:
            return _no_relevant_sources(None)

        n_results = min(max(1, retriever_settings.top_k), available_count)
        result = collection.query(
            query_texts=[question],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except FinanceQAError:
        raise
    except Exception as exc:
        raise FinanceQAError("Finance Q&A retrieval failed.") from exc

    documents = (result.get("documents") or [[]])[0] or []
    metadatas = (result.get("metadatas") or [[]])[0] or []
    distances = (result.get("distances") or [[]])[0] or []

    nearest_candidate = min(
        zip(documents, metadatas, distances),
        key=lambda hit: hit[2],
        default=None,
    )

    grouped_sources: dict[str, dict[str, object]] = {}
    retrieved_chunks: list[RetrievedChunk] = []

    for document, metadata, distance in zip(documents, metadatas, distances):
        if not isinstance(document, str) or distance > DISTANCE_THRESHOLD:
            continue

        metadata = metadata or {}
        clean_metadata = {
            key: value
            for key, value in metadata.items()
            if isinstance(value, (str, int, float, bool))
        }
        title = str(clean_metadata.get("title") or "Untitled source")
        url = str(clean_metadata.get("source_url") or "")
        source_key = url or str(clean_metadata.get("article_id") or title)

        retrieved_chunks.append(
            {
                "text": document,
                "metadata": clean_metadata,
                "distance": float(distance),
            }
        )

        if source_key not in grouped_sources:
            citation: SourceCitation = {
                "title": title,
                "url": url,
                "distance": float(distance),
            }
            grouped_sources[source_key] = {"citation": citation, "texts": []}

        source_group = grouped_sources[source_key]
        texts = source_group["texts"]
        if isinstance(texts, list) and document not in texts:
            texts.append(document)

        citation = source_group["citation"]
        if isinstance(citation, dict):
            citation["distance"] = min(citation["distance"], float(distance))

    if not grouped_sources:
        nearest_distance = (
            float(nearest_candidate[2]) if nearest_candidate is not None else None
        )
        nearest_metadata = nearest_candidate[1] if nearest_candidate is not None else {}
        nearest_title = (
            str(nearest_metadata.get("title") or "Untitled source")
            if nearest_metadata
            else None
        )
        return _no_relevant_sources(nearest_distance, nearest_title)

    sources = [group["citation"] for group in grouped_sources.values()]
    context_parts = []
    for source_index, group in enumerate(grouped_sources.values(), start=1):
        citation = group["citation"]
        title = citation["title"]
        source_text = "\n\n".join(group["texts"])
        context_parts.append(f"[Source {source_index} - {title}]\n{source_text}")

    context = "\n\n".join(context_parts)
    prompt = f"""
You are Finnie, an educational personal finance assistant.
Answer the user's question using only the supplied sources.
If the sources do not support an answer, say that the knowledge base does not
contain enough information. Do not invent facts, source labels, or URLs.
Use general educational language. Do not provide individualized investment,
tax, or legal advice. Cite supporting material using labels such as [Source 1].

Question: {question}

Sources:
{context}
"""

    try:
        llm_client = get_llm_client()
        interaction = llm_client.interactions.create(
            model=llm_settings.model,
            input=prompt,
        )
    except FinanceQAError:
        raise
    except Exception as exc:
        raise FinanceQAError("Gemini failed to generate the Finance Q&A answer.") from exc

    answer = interaction.output_text
    if not isinstance(answer, str) or not answer.strip():
        raise FinanceQAError("Gemini returned an empty Finance Q&A answer.")

    return {
        "retrieved_context": retrieved_chunks,
        "sources": sources,
        "response": answer.strip(),
        "error": "",
        "tool_result": {
            "distance_threshold": DISTANCE_THRESHOLD,
            "nearest_rejected_distance": _nearest_rejected_distance(distances),
        },
    }


def _nearest_rejected_distance(distances: list[float]) -> float | None:
    rejected = [float(distance) for distance in distances if distance > DISTANCE_THRESHOLD]
    return min(rejected) if rejected else None


def _no_relevant_sources(
    nearest_distance: float | None,
    nearest_title: str | None = None,
) -> dict[str, object]:
    tool_result: dict[str, object] = {
        "distance_threshold": DISTANCE_THRESHOLD,
        "nearest_rejected_distance": nearest_distance,
    }
    if nearest_title is not None:
        tool_result["nearest_rejected_title"] = nearest_title

    return {
        "retrieved_context": [],
        "sources": [],
        "response": (
            "I couldn't find sufficiently relevant information in Finnie's "
            "knowledge base to answer that. Try asking about a topic covered "
            "by the available finance education sources."
        ),
        "error": "",
        "tool_result": tool_result,
    }
