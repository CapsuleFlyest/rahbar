"""Indexer configuration, from the same ConfigMap the API reads (section 4.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexerSettings:
    embed_model: str        # EMBED_MODEL: must equal the API's value (section 4.4)
    chroma_host: str
    chroma_port: int
    collection: str
    corpus_dir: str         # where the documents and _index.json sit inside the Job's pod
    chunk_size: int         # in words (whitespace-separated tokens)
    chunk_overlap: int      # in words
    ollama_url: str
    chunk_strategy: str = "structure"   # CHUNK_STRATEGY: structure | fixed
    corpus_wait_seconds: int = 0        # CORPUS_WAIT_SECONDS: poll for documents this long
    chroma_wait_seconds: int = 120      # CHROMA_WAIT_SECONDS: retry the heartbeat this long
    embed_batch_size: int = 16          # EMBED_BATCH_SIZE
    ocr_lang: str = "eng"               # OCR_LANG
    ocr_dpi: int = 300                  # OCR_DPI


def get_settings() -> IndexerSettings:
    return IndexerSettings(
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=int(os.environ.get("CHROMA_PORT", 8000)),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        corpus_dir=os.environ.get("CORPUS_DIR", "/corpus"),
        chunk_size=int(os.environ.get("CHUNK_SIZE", 400)),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", 50)),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        chunk_strategy=os.environ.get("CHUNK_STRATEGY", "structure"),
        corpus_wait_seconds=int(os.environ.get("CORPUS_WAIT_SECONDS", 0)),
        chroma_wait_seconds=int(os.environ.get("CHROMA_WAIT_SECONDS", 120)),
        embed_batch_size=int(os.environ.get("EMBED_BATCH_SIZE", 16)),
        ocr_lang=os.environ.get("OCR_LANG", "eng"),
        ocr_dpi=int(os.environ.get("OCR_DPI", 300)),
    )
