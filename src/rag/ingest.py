import truststore

truststore.inject_into_ssl()

import re
from pathlib import Path

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
        body = re.split(r"(?im)^##\s+Source\s*$", body, maxsplit=1)[0].rstrip()
        if not body:
            raise ValueError(f"No article body found in {path}")
        articles.append((body, file_path.stem, metadata))

    return articles

def _split_long_unit(text: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph or bullet at sentence, then word boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            words = sentence.split()
            word_piece = ""
            for word in words:
                candidate = f"{word_piece} {word}".strip()
                if word_piece and len(candidate) > max_chars:
                    pieces.append(word_piece)
                    word_piece = word
                else:
                    word_piece = candidate
            if word_piece:
                pieces.append(word_piece)
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, chunk_size: int = 300, overlap: int = 100) -> list[str]:
    """Create chunks from Markdown sections, paragraphs, and individual bullets."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    heading_stack: list[tuple[int, str]] = []
    units: list[tuple[str, str]] = []

    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        heading_matches = [re.match(r"^(#{1,6})\s+(.+)$", line) for line in lines]
        if all(heading_matches):
            for match in heading_matches:
                level = len(match.group(1))
                heading_stack = [item for item in heading_stack if item[0] < level]
                heading_stack.append((level, match.group(0)))
            continue

        context = "\n".join(heading for _, heading in heading_stack)
        is_bullet_list = all(line.startswith(("- ", "* ")) for line in lines)
        content_units = lines if is_bullet_list else [" ".join(lines)]
        for unit in content_units:
            units.append((context, unit))

    chunks: list[str] = []
    current_context: str | None = None
    current_units: list[str] = []

    def render(context: str, content_units: list[str]) -> str:
        prefix = f"{context}\n\n" if context else ""
        return prefix + "\n".join(content_units)

    def flush() -> None:
        if current_units:
            chunks.append(render(current_context or "", current_units))

    for context, unit in units:
        prefix_size = len(context) + (2 if context else 0)
        max_content = max(1, chunk_size - prefix_size)
        parts = _split_long_unit(unit, max_content) if len(unit) > max_content else [unit]

        if context != current_context:
            flush()
            current_context = context
            current_units = []

        for part in parts:
            candidate = render(context, current_units + [part])
            if current_units and len(candidate) > chunk_size:
                previous_units = current_units
                flush()

                # Overlap only whole semantic units; never slice a word/sentence.
                carry: list[str] = []
                carry_size = 0
                for previous in reversed(previous_units):
                    added_size = len(previous) + (1 if carry else 0)
                    if carry_size + added_size > overlap:
                        break
                    carry.insert(0, previous)
                    carry_size += added_size

                while carry and len(render(context, carry + [part])) > chunk_size:
                    carry.pop(0)
                current_units = carry

            current_units.append(part)

    flush()
    return chunks

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

        chunk = chunk_text(body, chunk_size=300, overlap=100)
        chunk_ids = [f"{article_id}_chunk_{i}" for i in range(len(chunk))]
        chunk_metadatas = [
            {
                **{field: metadata[field] for field in required_fields},
                "article_id": article_id,
                "chunk_index": i,
            }
            for i in range(len(chunk))
        ]

        existing = collection.get(include=["metadatas"])

        article_ids =  [article_id for _, article_id, _ in articles]
        existing = collection.get(include=["metadatas"])
        old_article_ids = [
            record_id
            for record_id in existing["ids"]
            if record_id in article_ids
        ]

        if old_article_ids:
            collection.delete(ids=old_article_ids)
            print(f"Removed {len(old_article_ids)} old whole-article records.")

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

        existing_article_chunks = collection.get(
            where={"article_id": article_id},
            include=["metadatas"],
        )
        if existing_article_chunks["ids"]:
            collection.delete(ids=existing_article_chunks["ids"])

        # Stable ID + upsert makes repeated runs safe.
        collection.upsert(
            ids=chunk_ids,
            documents=chunk,
            metadatas=chunk_metadatas,
        )
        print(f"Indexed '{metadata['title']}' in {DB_DIRECTORY}")
   
    questions = [
                 "Can a portfolio of several sector ETFs still be concentrated?", 
                 "Could several sector ETFs still leave me concentrated?",    
                 "What are the mutual funds and how to buy them?",
                 "What are the risks of investing in sector ETFs?",
                 "What is an emergency funds? Why we need it?",
                 "How can savings help reduce financial risk?",
                 "How can I diversify my investments?",
                 "What are the tax implications of investing in sector ETFs?",
                 "How we can buy and sell ETFs? What are the steps to buy ETFs?",
                 "Who is Mayank Gaur?",
                 "What is the main use of Python Programming language?"]
    index = 1
    for question in questions:
        result = collection.query(
            query_texts=[question],
            n_results=1,
        )
        if not result["documents"] or not result["documents"][0]:
            print(f"\nQuestion {index}: {question}")
            print("No matching article was retrieved.")
            index += 1
            continue

        print(f"\nQuestion {index}: {question}")
        
        hits = zip(
            result["documents"][0],
            result["ids"][0],
            result["metadatas"][0],
            result["distances"][0],
        )
        for rank, (document, chunk_id, source, distance) in enumerate(hits, start=1):
            print(f"\nRank {rank} - distance: {distance}")
            if distance <= 1.00:
                print(f"Retrieved passage:\n{document}")
                print(f"Chunk ID: {chunk_id}")
                print(f"Source: {source['title']} - {source['publisher']}")
                print(f"URL: {source['source_url']}")
                print(f"Reviewed: {source['reviewed_date']}")
            else:
                print("No relevant passage found within the distance threshold.")

        index += 1
if __name__ == "__main__":
    main()
