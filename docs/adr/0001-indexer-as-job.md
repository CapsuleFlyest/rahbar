# ADR 0001: The indexer is a Job, not API startup code

<!-- DRAFT written with AI help. Rewrite in your own words before submitting (handout 4.2). -->

## Status
Accepted · 2026-11

## Context
The api runs 3 replicas and Chroma has one volume. Indexing means extracting, OCR-ing and
embedding PDFs: slow, memory-hungry, and it writes to the vector store.

## Decision
A Kubernetes Job (`k8s/base/indexer-job.yaml`) is the only writer. The api only reads. Re-indexing is
`kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar`; a weekly CronJob does it too.
While re-indexing, the indexer upserts the new chunks and then prunes stale ids (see `store.py`), so
the collection is never empty while the api serves. If the embedding model or dimension changes it
must delete and recreate the collection (readiness drops until it finishes).

## Options considered
Indexing in api startup: three pods race to write one PVC, every restart pays the full cost,
readiness lies or times out, and re-indexing needs a redeploy. Rejected.

## Consequences
Readiness (`/readyz`) must check the collection is non-empty so pods wait for the index.
The cache is namespaced by the collection's `index_id`, so a new index invalidates old answers.
