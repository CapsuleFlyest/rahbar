"""Runtime configuration, read once from environment variables.

On the cluster these variables come from your ConfigMap and Secret (section 4.1).
Nothing here is baked into the image, so one image runs in every environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Which implementations to load. "stub" needs no cluster, no model, no network.
    retriever: str = "stub"          # RETRIEVER: stub | chroma
    llm_provider: str = "stub"       # LLM_PROVIDER: stub | ollama-host | ollama-incluster | hosted

    # The embedding pin (section 4.4). The indexer reads the same ConfigMap key.
    embed_model: str = "nomic-embed-text"

    # Vector store
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    collection: str = "rahbar"

    # Retrieval and generation
    top_k: int = 5
    temperature: float = 0.2
    llm_model: str = "llama3.2:3b"
    ollama_url: str = "http://host.minikube.internal:11434"
    hosted_base_url: str = ""        # e.g. an OpenAI-compatible endpoint
    llm_api_key: str = field(default="", repr=False)   # from the Secret; never log it
    llm_timeout_seconds: float = 60.0   # TOTAL budget for one generation, retries included
    llm_max_retries: int = 2            # extra attempts after a 429 or 5xx (hosted provider)
    llm_retry_max_wait_seconds: float = 20.0   # longest single wait; a longer Retry-After gives up

    # Grounding (section 3.4): below this cosine similarity a passage is not evidence.
    relevance_floor: float = 0.50

    # Semantic cache (section 3.3)
    cache_enabled: bool = True
    cache_threshold: float = 0.92
    cache_ttl_seconds: int = 86400
    redis_host: str = "redis"
    redis_port: int = 6379

    # Readiness: auto = full dependency checks only when RETRIEVER=chroma; on | off force it.
    ready_checks: str = "auto"

    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings(
        retriever=os.environ.get("RETRIEVER", "stub"),
        llm_provider=os.environ.get("LLM_PROVIDER", "stub"),
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=_int("CHROMA_PORT", 8000),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        top_k=_int("TOP_K", 5),
        temperature=_float("TEMPERATURE", 0.2),
        llm_model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        hosted_base_url=os.environ.get("HOSTED_BASE_URL", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_timeout_seconds=_float("LLM_TIMEOUT_SECONDS", 60.0),
        llm_max_retries=_int("LLM_MAX_RETRIES", 2),
        llm_retry_max_wait_seconds=_float("LLM_RETRY_MAX_WAIT_SECONDS", 20.0),
        relevance_floor=_float("RELEVANCE_FLOOR", 0.50),
        cache_enabled=_bool("CACHE_ENABLED", True),
        cache_threshold=_float("CACHE_THRESHOLD", 0.92),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 86400),
        redis_host=os.environ.get("REDIS_HOST", "redis"),
        redis_port=_int("REDIS_PORT", 6379),
        ready_checks=os.environ.get("READY_CHECKS", "auto").strip().lower(),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
