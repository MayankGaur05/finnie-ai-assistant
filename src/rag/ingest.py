from pathlib import Path

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
print(f"Project root directory: {PROJECT_ROOT}")

ARTICLE_PATH = PROJECT_ROOT / "knowledge_base" / "articles" / "diversification.md"

DB_DIRECTORY = PROJECT_ROOT / "src" / "data" / "vector_store"

COLLECTION_NAME = "finnie_finance_education"

def read_article(path: Path) -> tuple[str, str, dict[str, str]]:
    """Return the article body, stable ID, and front-matter metadata."""
    content = path.read_text(encoding="utf-8")
    parts = content.split("---", maxsplit=2)

    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"Expected YAML front matter delimited by --- in {path}")

    metadata: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"').strip("'")

    body = parts[2].strip()
    if not body:
        raise ValueError(f"No article body found in {path}")

    return body, path.stem, metadata


def main() -> None:
    body, article_id, metadata = read_article(ARTICLE_PATH)

    required_fields = ("title", "publisher", "source_url", "topic", "reviewed_date")
    missing_fields = [field for field in required_fields if not metadata.get(field)]
    if missing_fields:
        raise ValueError(f"Missing article metadata: {', '.join(missing_fields)}")

    DB_DIRECTORY.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(DB_DIRECTORY))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    existing = collection.get(include=["metadatas"])

    legacy_ids = [
        record_id
        for record_id, metadata in zip(existing["ids"], existing["metadatas"])
        if metadata
        and metadata.get("source") == ARTICLE_PATH.name
        and "source_url" not in metadata
    ]

    if legacy_ids:
        collection.delete(ids=legacy_ids)
        print(f"Removed {len(legacy_ids)} legacy chunks.")

    # Stable ID + upsert makes repeated runs safe.
    collection.upsert(
        ids=[article_id],
        documents=[body],
        metadatas=[{field: metadata[field] for field in required_fields}],
    )
    print(f"Indexed '{metadata['title']}' in {DB_DIRECTORY}")

    question = "Does owning several funds guarantee diversification?"
    result = collection.query(
        query_texts=[question],
        n_results=1,
    )

    if not result["documents"] or not result["documents"][0]:
        print("No matching article was retrieved.")
        return

    print(f"\nQuestion: {question}")
    print(f"Retrieved passage:\n{result['documents'][0][0]}")

    source = result["metadatas"][0][0]
    print(f"\nSource: {source['title']} — {source['publisher']}")
    print(f"URL: {source['source_url']}")
    print(f"Reviewed: {source['reviewed_date']}")


if __name__ == "__main__":
    main()