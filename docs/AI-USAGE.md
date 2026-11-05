# AI usage

**Team:** CapsuleFlyer and AbubakrQ. **Tool:** Claude (Anthropic), used through Claude Code / claude.ai.

We used Claude to produce a first working scaffold of the system from the assignment handout and the starter kit.
All generated code was run against its own tests (run `make test`; counts are in the CI log), `ruff` and `mypy`; Kubernetes manifests and
Dockerfiles have since been run on minikube (see the last column); the workflows are still to be run. We review, run, and adjust everything
before submission; the last column records what we changed afterwards.

| Area | What Claude wrote or shaped | What we changed afterwards, and why (draft from git history and our debugging chats; check and reword) |
| --- | --- | --- |
| API retrieval and grounding (`api/app/retrieval`, `services/grounding.py`, `prompt.py`, `intent.py`) | Chroma retriever with superseded filtering, relevance floor and abstention, prompt with delimited evidence, citation check, validation with one retry and a safe fallback | Ran it on the real index: a cited answer, a refusal for an uncovered topic, and a cache hit all behaved as intended. |
| Providers and embeddings (`providers/llm`, `embedding.py`) | Ollama and hosted providers behind the starter interface, query embedding | Groq retired `llama-3.1-8b-instant` (HTTP 404 in the api log), so we switched to `openai/gpt-oss-20b`; rewrote `hosted.py` to retry 429/5xx with Retry-After inside one 45 s budget and never log the key (9 new tests). |
| Semantic cache and readiness (`services/cache.py`, `readiness.py`) | Redis cache keyed by index generation with never-cache rules; `/readyz` checks and the embedding-pin guardrail | Added tests for the readiness pin check and the cache (commit 97bf907). |
| Metrics and logging | Added counters, histograms, an in-flight gauge and per-request log fields | Nothing changed yet. |
| Indexer (`indexer/pipeline`) | Extraction with table handling and OCR, cleaning rules, structure-aware chunking, Ollama embedding, upsert-and-prune storing with pin metadata | The first version took page footers and table rows as headings, so every citation had a junk section. Changed it to font-size headings with two-column reading order, fixed overlap on long paragraphs, and marked only SRD 5.1 as superseded (commits 4b2311f, 97bf907). |
| Evaluation (`eval/run_eval.py`, `eval/golden.yaml`) | recall@k, citation validity, abstention correctness, CI gate; a draft golden set (questions to be verified against the real PDFs) | Added pacing and retry for the Groq rate limit and more golden questions (commits 497920f, 55f8e74). Golden section names still to be confirmed against the stored chunks. |
| Kubernetes (`k8s/`) | All required objects, base plus dev/prod/ci overlays, NetworkPolicies, probes, security contexts | Running it found two bugs: the Service named `chroma` injected `CHROMA_PORT` and crashed Chroma (`enableServiceLinks: false`), and Ollama on the host was unreachable, so it now runs as a container at 192.168.49.10 with matching NetworkPolicy rules. Also learned that deleting an indexer pod exhausts `backoffLimit`. |
| Containers and CI/CD (`*/Dockerfile`, `.github/workflows`, `scripts/`) | Multi-stage Dockerfiles, `ci.yml`, `cd.yml`, helper scripts, Makefile targets | Made the scripts executable (mode 100755) and installed poppler for `fetch.py`. First workflow runs: to be filled. |
| Documentation (`README.md`, `docs/adr/*`, `docs/ARCHITECTURE.md`) | First drafts, to be rewritten in our own words | README rewritten for WSL, Groq and the Ollama container, with a troubleshooting table; ADR 0004 rewritten; corpus docs updated. ADR 0001-0003 still to be reworded by us. |
| Tests | Unit tests for every module above, with stubs and fakes (no network, no model) | Added tests for the readiness pin, retriever, cache, embed and store, and the hosted provider. |
