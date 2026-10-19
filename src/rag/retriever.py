from google import genai 
from src.core import settings
import chromadb
import yaml
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

config_file_path = Path(__file__).resolve().parents[2] / "config.yaml"

llm_provider_settings = settings.Settings(config_file_path).llm_provider_settings
#print(f"LLM Provider Settings: {llm_provider_settings}")
retriever_settings = settings.Settings(config_file_path).retriever_settings
#print(f"Retriever Settings: {retriever_settings}")
db_directory_path = settings.Settings(config_file_path).db_directory_path
#print(f"Database Directory Path: {db_directory_path}")

chroma_client = chromadb.PersistentClient(path=str(db_directory_path))
collection = chroma_client.get_collection(name= retriever_settings.collection_name)


user_query = "What is an emergency funds? Why we need it?"

context = collection.query(
    query_texts= [user_query],
    n_results=1
)['documents'][0]

api_key = os.getenv("GEMINI_API_KEY")

llm_client = genai.Client(api_key=api_key)

prompt = f"{user_query}. Use this as context for answering: {context}"

interaction = llm_client.interactions.create(
    model= llm_provider_settings.model,
    input=prompt

)

print(f"Response from LLM: {interaction.output_text}")
