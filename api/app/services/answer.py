"""Turns a question into an AskResponse: the query pipeline of section 3.2.

 1 receive/validate (the route)  2 cache check  3 embed  4 retrieve (+ superseded filter)
 5 augment  6 generate  7 validate (+ retry, fallback)  8 store (+ cache)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider, Usage
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import Answer, AskResponse, Passage, RetrievedRef
from . import cache as cache_mod
from .grounding import (
    abstention_answer,
    apply_floor,
    fallback_answer,
    generate_with_validation,
)
from .intent import is_followup, wants_older_version

log = logging.getLogger("rahbar.answer")


def _response(
    answer: Answer, passages: list[Passage], provider_name: str, cached: bool = False
) -> AskResponse:
    return AskResponse(
        request_id=request_id_var.get(),
        answer=answer.answer,
        citations=answer.citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[
            RetrievedRef(chunk_id=p.chunk_id, source=p.source, section=p.section,
                         page=p.page, score=p.score)
            for p in passages
        ],
        provider=provider_name,
        cached=cached,
    )


def answer_question(
    question: str,
    retriever: Retriever,
    provider: LLMProvider,
    settings: Settings,
    cache: cache_mod.SemanticCache | None = None,
) -> AskResponse:
    followup = is_followup(question)
    include_old = wants_older_version(question)
    fields: dict[str, Any] = {
        "retriever": retriever.name, "provider": provider.name, "top_k": settings.top_k,
        "followup": followup, "include_superseded": include_old, "cached": False,
        "abstention": False, "fallback": None, "chunk_ids": [], "scores": [],
        "answered_from_context": False,
    }

    # 3. embed once; the same vector serves the cache lookup and the retrieval
    started = time.perf_counter()
    try:
        vector = retriever.embed_query(question)
    except Exception as exc:
        metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - started)
        return _failed("embedding_error", exc, fields, provider.name)

    # 2. cache check (skipped for follow-ups and when there is no vector)
    if cache is not None and vector is not None and not followup:
        hit = cache.lookup(vector, include_old)
        metrics.CACHE_REQUESTS.labels(result="hit" if hit else "miss").inc()
        if hit:
            response = AskResponse(**{**hit, "request_id": request_id_var.get(), "cached": True})
            fields.update(cached=True, answered_from_context=response.answered_from_context,
                          chunk_ids=[r.chunk_id for r in response.retrieved])
            log.info("answered", extra=fields)
            return response

    # 4. retrieve (superseded documents filtered unless the user asked about an old version)
    try:
        retrieved = retriever.retrieve(question, k=settings.top_k, vector=vector,
                                       include_superseded=include_old)
    except Exception as exc:
        metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - started)
        return _failed("retrieval_error", exc, fields, provider.name)
    metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - started)
    fields.update(chunk_ids=[p.chunk_id for p in retrieved],
                  scores=[round(p.score, 4) for p in retrieved])

    # relevance floor: abstain honestly, without spending an LLM call
    evidence = apply_floor(retrieved, settings.relevance_floor)
    if not evidence:
        metrics.ABSTENTIONS.inc()
        fields.update(abstention=True)
        log.info("answered", extra=fields)
        return _response(abstention_answer(), retrieved, provider.name)

    # 5-7. augment, generate, validate (one retry, then the canned fallback)
    usage = Usage()
    gen_started = time.perf_counter()
    outcome = generate_with_validation(provider, question, evidence, usage)
    metrics.GENERATION_LATENCY.observe(time.perf_counter() - gen_started)
    metrics.TOKENS.labels(direction="in").inc(usage.tokens_in)
    metrics.TOKENS.labels(direction="out").inc(usage.tokens_out)
    if outcome.citations_dropped:
        metrics.CITATIONS_DROPPED.inc(outcome.citations_dropped)
    answer = outcome.answer
    if outcome.fallback_reason:
        metrics.FALLBACKS.labels(reason=outcome.fallback_reason).inc()
    elif not answer.answered_from_context:
        metrics.ABSTENTIONS.inc()
        fields.update(abstention=True)
    fields.update(answered_from_context=answer.answered_from_context,
                  fallback=outcome.fallback_reason,
                  citations_dropped=outcome.citations_dropped)
    log.info("answered", extra=fields)

    # 8. store the turn in the cache, if it is safe to serve to everyone
    response = _response(answer, retrieved, provider.name)
    if (cache is not None and vector is not None
            and cache_mod.should_cache(answer.answered_from_context, outcome.fallback_reason,
                                       followup)):
        cache.store(vector, include_old, response.model_dump())
    return response


def _failed(reason: str, exc: Exception, fields: dict[str, Any], provider_name: str) -> AskResponse:
    metrics.FALLBACKS.labels(reason=reason).inc()
    fields.update(fallback=reason)
    log.warning("answered", extra={**fields, "error": f"{type(exc).__name__}: {exc}"[:200]})
    return _response(fallback_answer(reason), [], provider_name)
