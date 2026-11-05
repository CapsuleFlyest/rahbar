# What is still open

Written by hand, kept honest. Delete this file before submitting.

## Done and verified on minikube
Cluster, images, indexer Job (6 documents), api 3/3 ready, a cited answer, an abstention, a cache hit.

## Needs GitHub (nothing here can be faked)
1. Protect `main` (ruleset: PR + 1 approval + required checks, no bypass), add `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`, add the partner as a collaborator, edit PR #1 to name the corpus.
2. A PR that fails the eval gate (screenshot the greyed merge button), the fix (screenshot green), a successful `cd.yml` run with SHA-tagged images on Docker Hub.

## Needs the running system (re-index first if the indexer code changed since the last run)
3. `python eval/inspect_golden.py`: confirm every `section` in `eval/golden.yaml`, fix the two "Armor" entries, add one question about the scanned errata.
4. Check the absent topics really are absent: `for f in corpus/raw/*.pdf; do echo $f; pdftotext -q "$f" - | grep -ic -e "mind flayer" -e warlord; done` (the SRD and the Compendium must print 0 for mind flayer; if one does not, change the absent topic in `golden.yaml` and `docs/CORPUS.md`).
5. `python eval/run_eval.py --update-baseline`; commit `eval/results.json` and `eval/baseline.json`.
6. Three (size, overlap) runs for `docs/PIPELINE.md`; set `RELEVANCE_FLOOR` (mind-flayer chunks scored 0.58-0.60, above the 0.50 floor) and `CACHE_THRESHOLD` from data.
7. Break four stages for `docs/FAILURE-ANALYSIS.md`.
8. Evidence in `docs/evidence/`: branch protection, blocked merge, `kubectl get endpoints`, `kubectl get hpa`, rollout and undo, deleted pod, the EMBED_MODEL mismatch demo (api at 0/1 with the conflict in the log).

## Writing that has to be yours
9. ADR 0001-0003 in your own words (remove the DRAFT comments), the seven answers in `docs/ENGINEERING-NOTES.md`, the last column of `docs/AI-USAGE.md`.
10. `python scripts/check_submission.py` until clean.
