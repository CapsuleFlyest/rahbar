# Failure analysis

Method. For each stage of the pipeline (A extraction, B chunking, C retrieval, D prompt, E source, F generation) we break it on purpose,
one stage at a time, with `scripts/run-experiment.sh` (which changes the ConfigMap, re-indexes if chunking changed, flushes the cache and runs
`eval/golden.yaml` against the live API), then restore. Per stage: the symptom, the diagnosis, the stage, the remedy, and the number in our metrics or logs that would
have shown it if we had not caused it. From the lecture: only F is the model's fault, so check A to E first.

The signals we read: the one-line-per-request log (`top_k`, `chunk_ids`, `scores`, `abstention`, `fallback`, `answered_from_context`, `citations_dropped`),
the answer's `retrieved[]` list, and the Prometheus series `rahbar_retrieval_seconds`, `rahbar_generation_seconds`, `rahbar_abstentions_total`,
`rahbar_fallbacks_total`, `rahbar_citations_dropped_total`, `rahbar_cache_requests_total` (`api/app/routes/metrics.py`).

| Stage | How we break it | Status |
| --- | --- | --- |
| A Extraction | index the scanned PDF without OCR | not run (see "Found by accident" for two real stage A failures) |
| B Chunking | `CHUNK_STRATEGY=fixed CHUNK_SIZE=100 CHUNK_OVERLAP=0` | run: fill the result below |
| C Retrieval | `TOP_K=1` | run: fill the result below |
| D Prompt | delete the "use only the supplied context" instruction | run: fill the result below |
| E Source | remove the superseded filter, ask a version question | not run (q09 to q11 cover it in the golden set) |
| F Generation | `TEMPERATURE=1.2` | run: fill the result below |

## B. Chunking: fixed 100-word chunks with no overlap

Command: `scripts/run-experiment.sh run fail-b-fixed-chunks CHUNK_STRATEGY=fixed CHUNK_SIZE=100 CHUNK_OVERLAP=0`, then `scripts/run-experiment.sh restore --reindex`.

- **Expected symptom.** Answers that start or stop mid-rule: a definition cut in half, a table row separated from its header, so recall@5 drops and "answered_from_context=False" rises for multi-sentence rules.
- **Observed.** recall@3 / recall@5 / abstentions: **[from eval/experiments/fail-b-fixed-chunks.json]** against baseline **[from eval/baseline.json]**.
- **Diagnosis.** Compare `retrieved[].section` and the chunk count in the indexer's `embedded` log line (the chunk count roughly doubles to quadruples with 100-word chunks) against the baseline index.
- **Stage.** B (chunking), not the model: the same question retrieves worse passages.
- **Which number shows it.** recall@5 in `eval/results.json`, and `chunks` in the indexer log, the first thing that changed.
- **Remedy.** Structure-aware chunking under a size budget with overlap (`indexer/pipeline/chunk.py`), as in the baseline.

## C. Retrieval: top_k = 1

Command: `scripts/run-experiment.sh run fail-c-topk-1 TOP_K=1`, then `scripts/run-experiment.sh restore`.

- **Expected symptom.** Questions whose answer spans two chunks lose the second one; the right section is only found when it is the single nearest chunk. Citations shrink to one.
- **Observed.** recall@5 cannot exceed the share of questions whose single best chunk is right: **[from eval/experiments/fail-c-topk-1.json]**.
- **Diagnosis.** The request log shows `top_k: 1` and a one-element `chunk_ids`; the answer's `retrieved[]` has one entry.
- **Stage.** C (retrieval).
- **Which number shows it.** `top_k` and `scores` in the per-request log line, and recall@5 versus recall@3 collapsing to the same value.
- **Remedy.** `TOP_K` back to 5 in the ConfigMap (`k8s/base/configmap.yaml:41`).

## D. Prompt: no instruction to use only the supplied context

Edit the system prompt (`api/app/services/prompt.py`), `make images`, then `scripts/run-experiment.sh run fail-d-no-instruction`. Undo, rebuild, restore.

- **Expected symptom.** The model answers from its own memory when retrieval is poor, so the uncovered topics (mind flayers, Warlord) may get a confident answer and `answered_from_context` may be true with citations that were never retrieved. Those are dropped by the citation check.
- **Observed.** Abstention correctness and citation validity: **[from eval/experiments/fail-d-no-instruction.json]**.
- **Diagnosis.** Retrieval is unchanged (same `chunk_ids` and `scores` as the baseline), yet answers differ, which points at the prompt; `rahbar_citations_dropped_total` rises if the model invents sources.
- **Stage.** D (prompt).
- **Which number shows it.** abstention correctness falling below 100% and `citations_dropped` above 0.
- **Remedy.** Restore the instruction and keep the evidence delimited as data; the abstention and citation checks in the CI gate catch a regression.

## F. Generation: temperature 1.2

Command: `scripts/run-experiment.sh run fail-f-temp TEMPERATURE=1.2`, then `scripts/run-experiment.sh restore`.

- **Expected symptom.** Same retrieval, but answers vary between runs, JSON that fails validation more often (more `fallbacks`), and occasional wrong numbers in an otherwise correct passage.
- **Observed.** `expect_hit_rate`, fallbacks, citation validity: **[from eval/experiments/fail-f-temp.json]**.
- **Diagnosis.** Retrieved chunks and scores are identical to the baseline, so A to E are cleared and only generation changed.
- **Stage.** F, the only stage that is the model's fault.
- **Which number shows it.** `rahbar_fallbacks_total` and the share of answers failing the `expect` check, with `scores` unchanged.
- **Remedy.** Temperature 0.2 for factual JSON (`k8s/base/configmap.yaml:28`); temperature 0 would not fix absent knowledge, only make a wrong answer repeatable.

## Found by accident (real failures, in the order we hit them)

**1. Page footers became section names (stage A, then B metadata).** Symptom: the first answer's citation read
`section: "182 System Reference Document 5.2.1"` and `retrieved[]` showed sections such as `MOD SAVE MOD SAVE MOD SAVE`. Diagnosis: the heading detector treated footer and table-row lines as headings, so every
chunk's `section` metadata was junk even though the text was right. Stage: A (extraction) leaking into B (chunk metadata). Remedy: detect headings by font size relative to the body text
(`indexer/pipeline/extract.py`), keep footers out. Number that showed it: the `section` field in `retrieved[]`; the golden set's section matching could not work at all until it was fixed.

**2. The SRD 5.1 "Exhaustion" heading was lost (stage A).** Symptom: golden question q11 (2014 exhaustion) never retrieved an "Exhaustion" section;
`eval/inspect_golden.py` printed `PROBLEM: q11: no wanted section in the top 5`. Diagnosis: a Chroma query for chunks of `srd-5-1-2014.pdf` containing "Exhaustion" returned only
"Food and Water" and "Paralyzed" (p.358), so the exhaustion table was stored under the wrong label, and `pdfplumber` showed the heading at 10.8 pt against 9.8 pt body text, a ratio of 1.10,
below our 1.15 threshold. Stage: A, not retrieval: the right text was found, labelled wrongly. Remedy: a bold line that is at least 8% bigger counts as a heading, footers and monster
"Actions" labels are excluded (`indexer/pipeline/extract.py`, commit "detect bold sub-size headings; ignore footers", four unit tests); a naive lower threshold alone brought the footers back.
Effect on q11 after re-indexing: **[from eval/results.json]**.

**3. The relevance floor cannot separate answerable from unanswerable questions (stage C).** Symptom: the uncovered mind-flayer question retrieved chunks scoring 0.718,
above our lowest answerable question (q13, 0.668), while the floor is 0.50. Diagnosis: `eval/inspect_golden.py` prints the top-1 score of every must-abstain question
and warns about the overlap. Stage: C. Remedy: abstention rests on the model's `answered_from_context` flag, which returned false for both must-abstain questions; hybrid retrieval would
sharpen the scores and we did not build it. Number that shows it: the top-1 scores in the inspection output versus `RELEVANCE_FLOOR`.

**4. A retired model looked like a broken pipeline (not one of A to F: the provider).** Symptom: every answer was the canned fallback "I could not produce a reliable answer",
with correct retrieval. Diagnosis: the request log line carried `"fallback": "provider_error"` and the warning `hosted call failed: HTTP 404`; Groq had retired `llama-3.1-8b-instant`.
Remedy: `openai/gpt-oss-20b`, plus retries with backoff for HTTP 429 (`api/app/providers/llm/hosted.py`). Number that shows it: `rahbar_fallbacks_total` rising while retrieval scores stay normal.
