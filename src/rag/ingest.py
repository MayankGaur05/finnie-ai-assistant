from pathlib import Path

import chromadb

db_directory = Path("src/data/vector_store")
if not db_directory.exists():
    print(f"Database directory '{db_directory}' not found.")
    db_directory.mkdir(parents=True)
knowledge_base_path = Path("knowledge_base/articles")

# create a Chroma client instance
chroma_client = chromadb.PersistentClient(db_directory)

# create or get a collection
collection = chroma_client.get_or_create_collection(name="finnie_finance_education")

if not knowledge_base_path.exists():
    print(f"Knowledge base path '{knowledge_base_path}' not found.")
else:
    print(f"Knowledge base path '{knowledge_base_path}' found.")

    with open(knowledge_base_path / "diversification.md", "r") as file:
        content = file.read()

    # Split the content into individual documents based on double newlines
    documents = [page.strip() for page in content.split("\n\n") if page.strip()]

    # Generate unique IDs and metadata for each document chunk
    ids = [f"doc_{i}" for i in range(len(documents))]
    metadata = [{"source": "diversification.md", "page": i} for i in range(len(documents))]

    # Add the documents to the collection
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadata
    )

    print(f"Successfully stored {len(documents)} chunks from '{knowledge_base_path / 'diversification.md'}' into Chroma DB!")
    print(f"Database saved locally to: {db_directory}")

    # Query the collection for relevant documents based on a question
    result = collection.query( 
        query_texts=["What is diversification?"],
        n_results=3
    )

    print(f"Query result: {result}")
    