"""Prometheus metrics at /metrics (section 4.8)."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

router = APIRouter()

_SLOW_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120)

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
RETRIEVAL_LATENCY = Histogram(
    "rahbar_retrieval_seconds", "Embedding plus vector search latency", buckets=_SLOW_BUCKETS
)
GENERATION_LATENCY = Histogram(
    "rahbar_generation_seconds", "LLM generation latency (including the one retry)",
    buckets=_SLOW_BUCKETS,
)
CACHE_REQUESTS = Counter(
    "rahbar_cache_requests_total", "Semantic cache lookups; hit ratio = hit / (hit + miss)",
    ["result"],
)
ABSTENTIONS = Counter("rahbar_abstentions_total", "Questions the corpus could not answer")
FALLBACKS = Counter(
    "rahbar_fallbacks_total", "Canned fallback answers, by reason", ["reason"]
)
TOKENS = Counter("rahbar_tokens_total", "LLM tokens, by direction", ["direction"])
CITATIONS_DROPPED = Counter(
    "rahbar_citations_dropped_total", "Model citations that matched no retrieved passage"
)
# CPU is a poor signal for a service that mostly waits on the LLM (the pod is I/O bound).
# In-flight requests tracks how many users are waiting right now, so it is the signal an
# HPA should scale on (via a custom-metrics adapter). See docs/ENGINEERING-NOTES.md, Q3.
INFLIGHT = Gauge("rahbar_inflight_requests", "Requests currently being served")


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
