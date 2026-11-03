"""The indexer Job's entry point. It runs once and exits (section 4.2).

    python -m pipeline.run --dummy    # week 1: three fake chunks, no model needed
    python -m pipeline.run            # the real pipeline: extract, clean, chunk, embed, store

Exit code 0 means the index was written; anything else fails the Job, and
Kubernetes retries it up to the Job's backoffLimit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .config import IndexerSettings, get_settings
from .models import Chunk

DOC_SUFFIXES = {".pdf", ".md", ".html", ".htm", ".txt"}


def log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "msg": msg, **fields}), flush=True)


def _front_matter(path: Path) -> dict[str, str]:
    """Read `key: value` lines between leading '---' markers (used by eval/fixtures)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def discover(corpus_dir: str) -> list[tuple[Path, str, bool]]:
    """List (path, doc_version, superseded) for every document to index.

    corpus/fetch.py writes _index.json next to the files it downloads; use it when
    present. Otherwise read Markdown front matter (the CI fixtures work this way).
    """
    root = Path(corpus_dir)
    index = root / "_index.json"
    if index.exists():
        entries = json.loads(index.read_text(encoding="utf-8"))
        return [(root / e["file"], str(e.get("doc_version", "unknown")),
                 bool(e.get("superseded", False))) for e in entries]
    found = []
    for path in sorted(root.glob("*")):
        if path.suffix.lower() not in DOC_SUFFIXES:
            continue
        if path.name.lower().startswith("readme"):
            continue
        meta = _front_matter(path) if path.suffix.lower() == ".md" else {}
        found.append((path, meta.get("doc_version", "unknown"),
                      meta.get("superseded", "false").lower() == "true"))
    return found


def wait_for_corpus(settings: IndexerSettings) -> None:
    """Poll until the corpus directory holds documents (the Job may start before the
    corpus PVC is loaded), for at most CORPUS_WAIT_SECONDS."""
    deadline = time.monotonic() + settings.corpus_wait_seconds
    while True:
        if Path(settings.corpus_dir).is_dir() and discover(settings.corpus_dir):
            return
        if time.monotonic() >= deadline:
            raise SystemExit(f"no documents found in {settings.corpus_dir}")
        log("waiting for corpus", corpus_dir=settings.corpus_dir)
        time.sleep(5)


def wait_for_chroma(settings: IndexerSettings, client: Any | None = None) -> Any:
    """Retry the heartbeat until Chroma answers, for at most CHROMA_WAIT_SECONDS."""
    from .store import get_client

    deadline = time.monotonic() + settings.chroma_wait_seconds
    while True:
        try:
            client = client or get_client(settings)
            client.heartbeat()
            return client
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise SystemExit(f"Chroma at {settings.chroma_host}:{settings.chroma_port} "
                                 f"did not answer: {exc}") from exc
            log("waiting for chroma", error=str(exc)[:120])
            time.sleep(3)


def run_pipeline(settings: IndexerSettings, client: Any | None = None) -> int:
    from .chunk import amplification, chunk, count_tokens
    from .clean import clean
    from .embed import embed, embedding_dimension
    from .extract import extract
    from .store import store

    wait_for_corpus(settings)
    documents = discover(settings.corpus_dir)
    client = wait_for_chroma(settings, client)
    all_chunks: list[Chunk] = []
    original_words = 0
    for path, doc_version, superseded in documents:
        raw = extract(str(path), doc_version, superseded,
                      ocr_lang=settings.ocr_lang, ocr_dpi=settings.ocr_dpi)
        doc = clean(raw)
        pieces = chunk(doc, settings.chunk_size, settings.chunk_overlap,
                       strategy=settings.chunk_strategy)
        words = sum(count_tokens(p.text) for p in doc.pages)
        log("chunked", source=path.name, doc_version=doc_version, superseded=superseded,
            pages=len(doc.pages), ocr_pages=sum(1 for p in doc.pages if p.ocr),
            words=words, chunks=len(pieces), amplification=amplification(doc, pieces))
        if not pieces:
            raise SystemExit(f"{path.name} produced 0 chunks: extraction found no text "
                             f"(a scanned PDF needs OCR; check tesseract-ocr in the image)")
        original_words += words
        all_chunks.extend(pieces)
    vectors = embed([c.text for c in all_chunks], settings)
    stored_words = sum(count_tokens(c.text) for c in all_chunks)
    log("embedded", chunks=len(all_chunks), dimension=embedding_dimension(vectors),
        embed_model=settings.embed_model,
        amplification=round(stored_words / original_words, 3) if original_words else 0.0,
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        chunk_strategy=settings.chunk_strategy)
    return store(all_chunks, vectors, settings, client)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the RAHBAR index, then exit.")
    parser.add_argument("--dummy", action="store_true", help="write three fake chunks")
    args = parser.parse_args()
    settings = get_settings()
    log("indexer starting", dummy=args.dummy, embed_model=settings.embed_model,
        collection=settings.collection, chroma=f"{settings.chroma_host}:{settings.chroma_port}",
        pod=os.environ.get("HOSTNAME", "-"))
    started = time.perf_counter()
    try:
        if args.dummy:
            from .dummy import write_dummy_index
            from .store import get_client

            count = write_dummy_index(settings, get_client(settings))
        else:
            count = run_pipeline(settings)
    except NotImplementedError as exc:
        log("indexer stage not implemented yet", error=str(exc))
        return 2
    log("indexer finished", chunks=count, seconds=round(time.perf_counter() - started, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
