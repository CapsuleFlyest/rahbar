# What is done and what is still yours (delete this file before submitting)

## Done (day 1)
- **api**: real retriever (Chroma, superseded filter), Ollama + hosted providers, relevance floor/abstention,
  Pydantic validation + one retry + fallback, citation check, prompt-injection delimiting, Redis semantic cache
  (invalidated by index id), /readyz with the embedding-pin guardrail, metrics. 34 tests pass.
- **indexer**: extract (pdfplumber, tables, OCR), clean, structure-aware chunk, embed (Ollama), store
  (upsert + prune, pin metadata). 19 tests pass (incl. starter tests).
- **eval/run_eval.py**: recall@3/5, citation validity, abstention, gate. `eval/golden.yaml` is a DRAFT.
- **k8s**: all required objects, dev/prod/ci overlays. **Dockerfiles**, **ci.yml**, **cd.yml**, Makefile targets.

## NOT verified here (no cluster, no Docker daemon, university site blocked from my sandbox)
Manifests were only YAML-parsed, never run through kubectl/kubeconform; Dockerfiles never built;
workflows never run. Expect small fixes. Chroma/Redis UIDs (1000/999) may need adjusting if a pod crashes.

## Yours, in order
1. `git init`; commit the ORIGINAL starter first if you can, then these changes in small conventional commits
   (feat:, ci:, docs:...). Create `dev`, protect `main` (PR + CI + 1 approval), **name your corpus in your first PR**.
2. (README badge and prod overlay already set to CapsuleFlyer/rahbar and capsulef.) Add Docker Hub secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
3. `make cluster`, `make images`, `make apply`; verify the minikube host IP in `k8s/base/networkpolicy.yaml`.
4. `cp corpus/sources.example.yaml` is already done as `corpus/sources.yaml`; run `make fetch`, check the 2023 PDF
   downloads, commit `corpus/MANIFEST.md`. Confirm the scanned PDF with `pdffonts`.
5. Write `eval/golden.yaml` for real (fill every `relevant`) BEFORE tuning; measure 3 chunk configs; set RELEVANCE_FLOOR/CACHE_THRESHOLD from data.
6. Run `--update-baseline`; commit `eval/baseline.json`, `results.json`, and `eval/fixtures/baseline.fixture.json` after the first green CI.
7. Fill docs: CORPUS, PIPELINE (numbers), FAILURE-ANALYSIS (break 4 stages), ENGINEERING-NOTES (7 answers with line numbers and `kubectl top` output),
   AI-USAGE (what you changed), rewrite the ADR drafts in your own words. Collect the 5 evidence screenshots.
8. `python scripts/check_submission.py` until clean.
