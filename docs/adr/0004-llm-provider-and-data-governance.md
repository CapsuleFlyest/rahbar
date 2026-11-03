# ADR 0004: Pluggable LLM provider and data governance

## Status
Accepted · 2026-11

## Context
The handout wants generation behind an interface selected by `LLM_PROVIDER`, with at least one mode fully supported.
Our laptops are too weak to run a useful generation model next to minikube, so local generation was not an option.

## Decision
`LLM_PROVIDER` selects stub, ollama-host, ollama-incluster or hosted behind one interface (`api/app/providers/llm`).
**We ship `hosted` against Groq's free tier** (`HOSTED_BASE_URL` and `LLM_MODEL` in the ConfigMap, OpenAI-compatible
`/chat/completions`). The key lives only in the `rahbar-secret` Secret, created with `make secret`, and is never committed.
Groq has no embedding model, so the pinned `EMBED_MODEL` (`nomic-embed-text`) is served by a small Ollama on the host,
for the api and the indexer alike. Tests and CI use the stub provider and need no network.

## Data governance
Only the question and the retrieved public passages leave the cluster, over HTTPS (the only internet egress the api
NetworkPolicy allows). The corpus is public D&D rules, so nothing private is sent. Logs hold ids and scores, not answers.
Groq's free tier is rate-limited per minute, so the api must back off and fall back safely instead of returning a 500.

## Consequences
Student questions go to a third party: users must not type personal data. Swapping provider is one file plus the ConfigMap.
Generation now depends on an external service, so a Groq outage or rate limit shows up as fallbacks, which the metrics count.
