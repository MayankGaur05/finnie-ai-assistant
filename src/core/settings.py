from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class LLMProviderSettings:
    provider: str
    model: str
    #api_key: str
    temperature: float
    max_output_tokens: int

@dataclass
class RetrieverSettings:
    provider: str
    client_type: str
    knowledge_base_path: str
    db_directory_path: str
    collection_name: str
    top_k: int


class Settings:
    def __init__(self, config_file_path):
        with open(config_file_path, 'r') as file:
            self.config = yaml.safe_load(file)
            self.llm_provider_settings = LLMProviderSettings(**self.config['llm'])
            self.retriever_settings = RetrieverSettings(**self.config['retrieval'])
            self.db_directory_path = self.get_db_directory_path()    

    def __get(self, key, default=None):
        return self.config.get(key, default)

    def get_db_directory_path(self): 
        PROJECT_ROOT = Path(__file__).resolve().parents[2]
        return PROJECT_ROOT / self.__get('retrieval', {}).get('db_directory_path', 'src/data/vector_store')