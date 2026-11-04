# AI usage

**Team:** CapsuleFlyer and AbubakrQ. **Tool:** Claude (Anthropic), used through Claude Code / claude.ai.

We used Claude to produce a first working scaffold of the system from the assignment handout and the starter kit.
All generated code was run against its own tests (run `make test`; counts are in the CI log), `ruff` and `mypy`; Kubernetes manifests,
Dockerfiles and workflows were generated but not yet run on a cluster. We review, run, and adjust everything
before submission; the last column records what we changed afterwards.

| Area | What Claude wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| API retrieval and grounding (`api/app/retrieval`, `services/grounding.py`, `prompt.py`, `intent.py`) | Chroma retriever with superseded filtering, relevance floor and abstention, prompt with delimited evidence, citation check, validation with one retry and a safe fallback | _to be filled after review and tuning_ |
| Providers and embeddings (`providers/llm`, `embedding.py`) | Ollama and hosted providers behind the starter interface, query embedding | _to be filled_ |
| Semantic cache and readiness (`services/cache.py`, `readiness.py`) | Redis cache keyed by index generation with never-cache rules; `/readyz` checks and the embedding-pin guardrail | _to be filled_ |
| Metrics and logging | Added counters, histograms, an in-flight gauge and per-request log fields | _to be filled_ |
| Indexer (`indexer/pipeline`) | Extraction with table handling and OCR, cleaning rules, structure-aware chunking, Ollama embedding, upsert-and-prune storing with pin metadata | _to be filled_ |
| Evaluation (`eval/run_eval.py`, `eval/golden.yaml`) | recall@k, citation validity, abstention correctness, CI gate; a draft golden set (questions to be verified against the real PDFs) | _to be filled_ |
| Kubernetes (`k8s/`) | All required objects, base plus dev/prod/ci overlays, NetworkPolicies, probes, security contexts | _to be filled after running on minikube_ |
| Containers and CI/CD (`*/Dockerfile`, `.github/workflows`, `scripts/`) | Multi-stage Dockerfiles, `ci.yml`, `cd.yml`, helper scripts, Makefile targets | _to be filled after the first workflow runs_ |
| Documentation (`README.md`, `docs/adr/*`, `docs/ARCHITECTURE.md`) | First drafts, to be rewritten in our own words | _to be filled_ |
| Tests | Unit tests for every module above, with stubs and fakes (no network, no model) | _to be filled_ |
