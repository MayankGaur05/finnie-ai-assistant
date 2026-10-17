import truststore

truststore.inject_into_ssl()

from pathlib import Path

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
print(f"Project root directory: {PROJECT_ROOT}")

ARTICLE_DIRECTORY_PATH = PROJECT_ROOT / "knowledge_base" / "articles" 

DB_DIRECTORY = PROJECT_ROOT / "src" / "data" / "vector_store"

COLLECTION_NAME = "finnie_finance_education"

def read_articles(path: Path) -> list[tuple[str, str, dict[str, str]]]:

    articles: list[tuple[str, str, dict[str, str]]] = []

    for file_path in path.glob("*.md"):    
        """Return the article body, stable ID, and front-matter metadata."""
        print(f"Reading article from {file_path}")
        content = file_path.read_text(encoding="utf-8")
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
        articles.append((body, file_path.stem, metadata))

    return articles


def main() -> None:
    articles = read_articles(ARTICLE_DIRECTORY_PATH)
    if not articles:
        raise ValueError(f"No articles found in {ARTICLE_DIRECTORY_PATH}")
    for body, article_id, metadata in articles:
        print(f"Processing article '{metadata.get('title', article_id)}' with ID '{article_id}'")

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
            and metadata.get("source") == ARTICLE_DIRECTORY_PATH.name
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
   
    questions = ["Can a portfolio of several sector ETFs still be concentrated?", 
                "What are the risks of investing in sector ETFs?",
                "What is an emergency funds? Why we need it?",
                "How can savings help reduce financial risk?",
                "How can I diversify my investments?", 
                "What are the tax implications of investing in sector ETFs?",
                "Who is Mayank Gaur?",
                "What is the main use of Python Programming language?"]
    index = 1
    for question in questions:
        result = collection.query(
            query_texts=[question],
            n_results=1,
        )

        if not result["documents"] or not result["documents"][0]:
            print("No matching article was retrieved.")
            continue
        elif (result['distances'][0][0]) <= 1:

            print(f"\nQuestion {index}: {question}")
            print(f"Retrieved passage:\n{result['documents'][0][0]}")

            source = result["metadatas"][0][0]
            print(f"\nSource: {source['title']} — {source['publisher']}")
            print(f"URL: {source['source_url']}")
            print(f"Reviewed: {source['reviewed_date']}")

            print(f"Result distance: {result['distances'][0]}")
        else:
            print(f"\nQuestion {index}: {question}")
            print(f"No relevant passage found within the distance threshold for Question {index}.")
            print(f"Result distance: {result['distances'][0]}")

        index += 1
if __name__ == "__main__":
    main()
