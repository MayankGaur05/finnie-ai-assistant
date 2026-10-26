from google import genai
from src.core import settings
import chromadb
from pathlib import Path
from dotenv import load_dotenv
import os
import truststore

truststore.inject_into_ssl()

# Load environment variables from .env file
load_dotenv()
# Load application settings from config.yaml
config_file_path = Path(__file__).resolve().parents[2] / "config.yaml"
app_settings = settings.Settings(config_file_path)
llm_provider_settings = app_settings.llm_provider_settings # llm settings are now loaded from config.yaml
retriever_settings = app_settings.retriever_settings # retriever settings are now loaded from config.yaml
db_directory_path = app_settings.db_directory_path # database directory path is now loaded from config.yaml

# Initialize the Chroma client and retrieve the collection
chroma_client = chromadb.PersistentClient(path=str(db_directory_path))
collection = chroma_client.get_collection(name=retriever_settings.collection_name)

# Matches the 1.00 retrieval cutoff already used in ingest.py and the evaluation runs.
DISTANCE_THRESHOLD = 1.00

# Define a list of user queries to test the retrieval and response generation
user_queries = [
     "What are the differences between checking and savings accounts?",
     "What is the difference between direct and indirect taxes in India?",
     "How do GST, customs duty, and excise duty fit into indirect taxation in India?",
     "What kinds of income may be considered when calculating income tax in India?",
     "Does every charitable donation qualify for a tax deduction in India?",
     "What is the difference between a tax deduction, a tax credit, and an exemption?",
     "What should I know about tax laws and the Income-tax Act 2025 in India?",
     "What should I compare before choosing a savings scheme in India?",
     "What costs and checks should I consider before buying a home in India?",
     "How can I make a household budget and plan savings in India?",
     "What does government policy mean, and which levels of government make policy in India?",
     "What is monetary policy in India and what role does the RBI's MPC have?",
     "What is fiscal policy and how do government spending and revenue affect the economy?",
     "What is the difference between microeconomics and macroeconomics?",
    # "Can a portfolio of several sector ETFs still be concentrated?",
    # "Could several sector ETFs still leave me concentrated?",
    # "What are the mutual funds and how to buy them?",
    # "What are the risks of investing in sector ETFs?",
    # "How can savings help reduce financial risk?",
    # "How can I diversify my investments?",
    # "How can I make a basic budget and track my cash flow?",
    # "What is the difference between stocks and bonds?",
    # "How can investment fees affect my returns over time?",
    # "What is return on investment (ROI), and how is it calculated?",
    # "What are common types of investments, such as REITs and commodities?",
    # "What are the tax implications of investing in sector ETFs?",
    # "How we can buy and sell ETFs? What are the steps to buy ETFs?",
    # "What is the main use of Python Programming language?",
]

# Set up the Gemini API client using the API key from environment variables
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing. Set it in the environment or project .env file.")

llm_client = genai.Client(api_key=api_key)

# Process each user query, retrieve relevant sources, and generate answers using the LLM
for idx, user_query in enumerate(user_queries, start=1):
    result = collection.query(
        query_texts=[user_query],
        n_results=3,
        include=["documents", "metadatas", "distances"],
    )

    # Extract the retrieved documents, metadata, and distances from the query result
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]
    
    # Find the nearest candidate regardless of the distance threshold for reporting purposes
    nearest_candidate = min(
        zip(documents, metadatas, distances),
        key=lambda hit: hit[2],
        default=None,
    )

    # Keep only matches within the evaluated cutoff and combine chunks from
    # the same article so each article appears as a single cited source.
    sources_by_url = {}
    for document, metadata, distance in zip(documents, metadatas, distances):
        if distance >= DISTANCE_THRESHOLD:
            continue

        title = metadata.get("title", "Untitled source")
        url = metadata.get("source_url", "")
        source_key = url or metadata.get("article_id", title)

        if source_key not in sources_by_url:
            sources_by_url[source_key] = {
                "title": title,
                "url": url,
                "texts": [],
                "distance": distance,
            }

        source = sources_by_url[source_key]
        if document not in source["texts"]:
            source["texts"].append(document)
        source["distance"] = min(source["distance"], distance)

    sources = list(sources_by_url.values())

    print(f"Query {idx}: {user_query}")
    if not sources:
        print(f"Answer: I couldn't find sufficiently relevant information in the knowledge base to answer that.")
        print(f"No sources passed the distance cutoff ({DISTANCE_THRESHOLD:.2f}).")
        if nearest_candidate is not None:
            _, nearest_metadata, nearest_distance = nearest_candidate
            nearest_title = nearest_metadata.get("title", "Untitled source")
            print(
                f"Nearest rejected candidate: {nearest_title} "
                f"(distance: {nearest_distance:.4f})"
            )
        else:
            print("Chroma returned no candidates.")
        continue

    context_parts = []
    for source_index, source in enumerate(sources, start=1):
        source_text = "\n\n".join(source["texts"])
        context_parts.append(
            f"[Source {source_index} - {source['title']}]\n{source_text}"
        )
    context = "\n\n".join(context_parts)

    prompt = f"""
Answer the question using only the supplied sources.
If they do not contain enough information, say so.
Cite supporting sources using their labels, such as [Source 1].
Do not invent source labels or URLs.

Question: {user_query}

Sources:
{context}
"""

    interaction = llm_client.interactions.create(
        model=llm_provider_settings.model,
        input=prompt,
    )

    print(f"Answer: {interaction.output_text}")
    print("Retrieved sources:")
    for source_index, source in enumerate(sources, start=1):
        print(
            f"[Source {source_index}] {source['title']} - {source['url']} "
            f"(best distance: {source['distance']:.4f})"
        )
