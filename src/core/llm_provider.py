import os
import truststore
from functools import lru_cache

truststore.inject_into_ssl()
from dotenv import load_dotenv

load_dotenv()
from google import genai

@lru_cache(maxsize=1)
def get_llm_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    
    return genai.Client(api_key=api_key)