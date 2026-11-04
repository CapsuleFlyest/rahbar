# What is still open

Written by hand, kept honest. Delete this file before submitting.

## Needs the cluster or GitHub (nothing here can be faked)
1. `make cluster`, `make images`, `kubectl apply -k k8s/overlays/dev`, `make corpus-load`, wait for the indexer Job.
2. GitHub: protect `main` (PR + CI + 1 approval), add `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`, open the first PR from `dev` naming the corpus.
3. Evidence screenshots in `docs/evidence/`: branch protection, the blocked merge, `kubectl top pods`, `kubectl get endpoints`, `kubectl get hpa`.

## Needs numbers from running the system
4. Indexer: headings from font size and two-column extraction, so `section` is a real heading and not a page footer.
5. Run `eval/run_eval.py`; confirm every `section` in `eval/golden.yaml`; fix the two "Armor" entries.
6. Measure three (size, overlap) configurations; set `RELEVANCE_FLOOR` and `CACHE_THRESHOLD` from data.
7. `--update-baseline`; commit `eval/baseline.json`, `eval/results.json`, `eval/fixtures/baseline.fixture.json`.
8. Fill `docs/PIPELINE.md`, `docs/FAILURE-ANALYSIS.md` (four broken stages), `docs/ENGINEERING-NOTES.md` (seven answers with line numbers), finish `docs/adr/0002`, update `docs/AI-USAGE.md`.
9. `python scripts/check_submission.py` until clean.
