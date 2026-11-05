# What is still open

Written by hand, kept honest. Delete this file before submitting.

## Done and verified
Cluster, images, indexer Job (6 documents), api 3/3 ready, a cited answer, an abstention, a cache hit.
CI review (offline): `ruff`, `mypy`, 79 api tests (91% coverage) and 50 indexer tests pass; the CI overlay's NetworkPolicy
patch paths match the base manifests. Nothing has run on GitHub Actions yet.

## 0. Make re-indexing fast (optional, saves hours)
A CPU-only Ollama took 36 minutes per index and you need about five more (three chunking sizes, one broken-chunking
experiment, one restore). With the RTX 3060 Ti it should take a few minutes:
```
docker run --rm --gpus all ubuntu nvidia-smi          # must print your GPU; if not, skip this section
docker rm -f ollama
docker run -d --name ollama --gpus all --network minikube --ip 192.168.49.10 \
  -v ollama-models:/root/.ollama --restart unless-stopped ollama/ollama
docker exec ollama ollama list                        # nomic-embed-text is still there (same volume)
```

## 1. GitHub (nothing here can be faked)
- Ruleset on `main`: PR + 1 approval, block force pushes, restrict deletions, no bypass. Required checks once CI has run once:
  `lint`, `test`, `manifests`, `build`, `scan (rahbar-api)`, `scan (rahbar-indexer)`, `scan (rahbar-ui)`, `e2e-eval`.
- Secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`; partner added as collaborator; PR #1 description names the corpus.
- **Fixture baseline (a real gap):** `eval/fixtures/baseline.fixture.json` does not exist, so the CI gate cannot check the
  recall@5 drop. After the first green `e2e-eval`, download the `eval-results` artifact, copy `results.fixture.json` to
  `eval/fixtures/baseline.fixture.json`, commit. Then open a PR that makes the gate fail (for example `TOP_K: "1"` in the
  ConfigMap), screenshot the grey merge button, revert, screenshot green.
- A successful `cd.yml` run (merge a PR to `main`), and the Docker Hub page showing SHA tags.

## 2. Evaluation (needs the live stack)
1. `python eval/inspect_golden.py` and fix any `section` that is not a stored section (the two "Armor" entries first).
2. Check the absent topics: `for f in corpus/raw/*.pdf; do echo $f; pdftotext -q "$f" - | grep -ic -e "mind flayer" -e warlord; done`
   (every file should print 0; if not, change the absent topic in `golden.yaml` and `docs/CORPUS.md`).
3. `python eval/run_eval.py --api http://localhost:8000 --delay 5 --update-baseline` (with `kubectl -n rahbar port-forward svc/api 8000:8000` running);
   commit `eval/results.json` and `eval/baseline.json`.

## 3. Measurements, one command each (`scripts/run-experiment.sh`)
Chunking table for `docs/PIPELINE.md` and ADR 0002:
```
scripts/run-experiment.sh run chunk-200-25 CHUNK_SIZE=200 CHUNK_OVERLAP=25
scripts/run-experiment.sh run chunk-400-50 CHUNK_SIZE=400 CHUNK_OVERLAP=50
scripts/run-experiment.sh run chunk-600-75 CHUNK_SIZE=600 CHUNK_OVERLAP=75
```
Failure analysis (four of six stages; each ends with `restore`):
```
scripts/run-experiment.sh run fail-b-fixed-chunks CHUNK_STRATEGY=fixed CHUNK_SIZE=100 CHUNK_OVERLAP=0   # B chunking
scripts/run-experiment.sh restore --reindex
scripts/run-experiment.sh run fail-c-topk-1 TOP_K=1                                                      # C retrieval
scripts/run-experiment.sh run fail-f-temp TEMPERATURE=1.2                                                # F generation
scripts/run-experiment.sh restore
# D prompt: delete the "use only the supplied context" sentence in SYSTEM_PROMPT (api/app/services/prompt.py),
#   make images, then: scripts/run-experiment.sh run fail-d-no-instruction ; undo the edit, make images, restore.
```
Cache threshold and relevance floor: `run thr-090 CACHE_THRESHOLD=0.90`, `run floor-065 RELEVANCE_FLOOR=0.65`, etc.
For each result open `eval/experiments/<name>.json` and note the symptom, the stage, the metric that showed it.

## 4. Evidence files (`scripts/collect-evidence.sh`, outputs land in `docs/evidence/`)
`safe` (endpoints, hpa, top), `delete-pod` (needs `minikube tunnel`), `pin-demo` (restores itself), and
`rollout ui:v2` after you change a visible string in `ui/`, build `rahbar-ui:v2` and `minikube image load rahbar-ui:v2`.
Also run `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar` once and save `kubectl -n rahbar get job` output.
Screenshots: branch protection, blocked merge, green merge.

## 5. Writing that has to be yours
ADR 0001-0003 in your own words (remove the DRAFT comments; 0002 gets the table), the seven answers in
`docs/ENGINEERING-NOTES.md`, `docs/FAILURE-ANALYSIS.md`, every **FILL** in `docs/PIPELINE.md`, the last column of
`docs/AI-USAGE.md`. Then `python scripts/check_submission.py` until clean and delete this file.
