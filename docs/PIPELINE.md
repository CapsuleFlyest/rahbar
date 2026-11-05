# Indexing and retrieval pipeline

<!-- STARTER-TODO(3.1, 3.3, 5.2): every **FILL** below needs a number or sentence from a real run. Then delete this comment. -->

Facts already true of the code are written out; each **FILL** is yours to measure or write.

## Extraction
- Digital PDFs: text in reading order, two-column pages read left column then right (`indexer/pipeline/extract.py:83`), headings found by font size, not by what the words look like (`indexer/pipeline/extract.py:113`).
- Tables become Markdown so columns do not come out jumbled (`indexer/pipeline/extract.py:38`).
- Pages with no text layer are OCR'd (`indexer/pipeline/extract.py:51`). In our run the scanned Player's Handbook errata needed OCR on all 5 of its 5 pages and no page came back empty.
- **FILL:** one before-and-after example of a mangled table (paste the raw text and the Markdown).
- **FILL:** what could not be recovered (for example OCR errors; compare against the text version of the same errata, which exists).

## Cleaning
- Rules are in `indexer/pipeline/clean.py`. **FILL:** list the rules you applied and one thing you deliberately did not strip (and why).

## Chunking
Structure-aware: sections, then paragraphs, then sentences, under a word budget with overlap (`indexer/pipeline/chunk.py:170`); tables are kept whole and split by rows with the header repeated (`indexer/pipeline/chunk.py:137`). Size and overlap are in **words** (whitespace-separated), not model tokens. Shipped values are `CHUNK_SIZE` and `CHUNK_OVERLAP` in `k8s/base/configmap.yaml:54`.

Storage amplification (stored words / original words) is printed by the indexer in its `embedded` log line: **FILL** (`kubectl -n rahbar logs job/indexer | grep embedded`).

Three configurations, measured with recall@5 on `eval/golden.yaml` (re-index for each; suggested sizes, change them if you prefer):

| Size (words) | Overlap (words) | recall@5 | Chunks stored |
| --- | --- | --- | --- |
| 200 | 25 | **FILL** | **FILL** |
| 400 (current) | 50 | **FILL** | **FILL** |
| 600 | 75 | **FILL** | **FILL** |

**FILL:** which one you shipped and why (the number, not a feeling). Copy the result into ADR 0002.

## Embedding
Model `nomic-embed-text`, vector dimension 768 (printed in the indexer's `embedded` line). The pin lives in `k8s/base/configmap.yaml:2`; the indexer writes the model name and dimension into the collection metadata (`indexer/pipeline/store.py:30`); the API compares them at `/readyz` and answers 503 naming the conflict (`api/app/readiness.py:28`).

## Semantic cache
Redis, cosine similarity against stored question vectors, threshold `CACHE_THRESHOLD` (`k8s/base/configmap.yaml:48`, currently 0.92). Entries are keyed by the indexer's `index_id`, so a re-index makes old answers unreachable (`indexer/pipeline/store.py:37`).
**FILL:** two or three thresholds you tried, the false hit that ruled one out, the one you shipped.

## Relevance floor
`RELEVANCE_FLOOR` is `k8s/base/configmap.yaml:44` (0.50). On the real index an uncovered question (mind flayers) retrieved chunks scoring 0.58 to 0.60, so the floor alone cannot make the system abstain; the model's `answered_from_context` flag did. **FILL:** the scores you measured for answerable and unanswerable questions, and the floor you chose.

## Evaluation method
A retrieved chunk matches a golden passage when the source file is equal and the section starts with the golden section (`eval/run_eval.py:98`); recall@k is relevant passages found in the top k over total relevant (`eval/run_eval.py:114`). Citation validity and abstention correctness are computed in the same file. **FILL:** recall@3 and recall@5 overall and by question type, from `eval/results.json`.
