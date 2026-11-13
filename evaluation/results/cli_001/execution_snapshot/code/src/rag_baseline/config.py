from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CorpusSource(BaseModel):
    path: Path
    id_prefix: str
    norm_name: str


class BaselineSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    OPENROUTER_API_KEY: SecretStr | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_APP_NAME: str = "normative-agentic-rag-ufpi"
    OPENROUTER_HTTP_REFERER: str | None = None
    OPENROUTER_TIMEOUT_SECONDS: float = 30

    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = 64

    LLM_MODEL: str = "qwen/qwen3-30b-a3b-instruct-2507"
    LLM_TEMPERATURE: float = 0
    LLM_MAX_TOKENS: int = 800

    RETRIEVAL_TOP_K: int = 5
    CHROMA_COLLECTION: str = "ufpi_graduacao_177_2012"
    CHROMA_PERSIST_DIR: Path = Path(".local/chroma")
    CORPUS_PATH: Path = Path("scripts/chunks_v2.json")
    CORPUS_ID_PREFIX: str = "ufpi-177-2012"
    CORPUS_NAME: str = "Resolução nº 177/2012 CEPEX/UFPI"
    CORPUS_SOURCES: tuple[CorpusSource, ...] = ()

    def api_key_value(self) -> str | None:
        return self.OPENROUTER_API_KEY.get_secret_value() if self.OPENROUTER_API_KEY else None
