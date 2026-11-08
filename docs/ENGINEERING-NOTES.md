# Engineering notes

Answers to the seven questions, pointing at our own files. Numbers marked **[from results.json]** are filled from
`eval/results.json` after the final evaluation run; everything else was measured or read from the repository.

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

Three pods would start the same extract, chunk, embed and write job against one Chroma store at once. Each pod would be
halfway through a different document, so the collection could end up in a state no complete pass produced (one writer's
chunks, another's half-written batch). The same design also re-indexes on every restart: a full run takes 36 minutes of
embedding on our CPU Ollama (`indexer finished ... "seconds": 2180.7` in the Job log), and a rolling update, an OOMKill or a node
drain would each pay it again. Readiness would become a lie: either the pod reports ready over an empty index and serves
empty retrievals, or it stays unready for 36 minutes while the startup probe, 30 failures x 2 s = 60 s
(`k8s/base/api-deployment.yaml:51-56`), kills it halfway. And any configuration change that needs a rebuild would need a redeploy.

What prevents it: the indexer is its own Job with `restartPolicy: OnFailure` and `backoffLimit: 3`
(`k8s/base/indexer-job.yaml:15`, `:10`), the only writer. Chroma is a StatefulSet with its own PVC
(`k8s/base/chroma-statefulset.yaml:95`, `volumeClaimTemplates`). The NetworkPolicy lets only the api and the indexer reach it
(`k8s/base/networkpolicy.yaml:49-50`), and the api code never writes (`grep` for upsert/add/delete in `api/app` finds nothing but a Python set).
`/readyz` answers 503 on an empty collection (`api/app/readiness.py:60-62`), so a pod stays out of the Service until the Job has
written. During a re-index `indexer/pipeline/store.py:64-115` upserts first and prunes stale ids afterwards, so the collection is never empty.
We saw this work: on first deploy the api pods sat at `0/1` logging `collection 'rahbar' not found`, and flipped to `1/1` after
the Job finished, with no restart.

## 2. Readiness depends on Chroma, liveness does not. What if we swapped them and Chroma is slow for 90 seconds?

Our probes: liveness `/healthz` every 20 s with `failureThreshold: 3`, readiness `/readyz` every 10 s with `failureThreshold: 3`
(`k8s/base/api-deployment.yaml:57-71`). `/healthz` touches nothing; `/readyz` checks Chroma, the collection, Redis and the embedding pin (`api/app/readiness.py:36-79`).

Swapped, liveness would fail after 3 x 20 s = 60 s, which is less than 90 s. The kubelet would restart the container in all
three pods at about the same moment, because they all depend on the same slow Chroma. During the restarts the Service has no
ready endpoint, so a slow dependency becomes a full outage; the new containers would fail liveness again while Chroma is still slow, and the
restart counters climb (a restart storm), with every restart discarding the in-memory state. Meanwhile readiness on `/healthz`
would keep the pods in the Service and send them traffic they cannot serve, so users would see errors instead of a clean "not ready".
With the correct arrangement, Chroma slowness removes the pods from the Service (503 on `/readyz`) and nothing is killed; when Chroma
recovers, the pods return within one readiness period.

## 3. While the model generates, what does a CPU-based HPA measure, and what should scale the service?

The HPA divides the api container's CPU usage by its CPU request: target 70% (`k8s/base/hpa.yaml:13`) of `requests.cpu: 100m`
(`k8s/base/api-deployment.yaml:74`), so it scales at about 70m per pod. While a request waits on Groq the pod is blocked on the network, so
CPU stays near zero: in `docs/evidence/kubectl-top-indexer.txt` the api pods sit at 4m (4% of the request) when idle, and a generation
call of about 2.8 s uses almost none of it. The HPA therefore measures how much Python work the pod is doing (JSON handling, embedding
calls, validation), not how many users are waiting, and it would not scale out while the pods queue requests.

The signal that matches the load is concurrency: requests in flight per pod, or generation latency. The api already exports
`rahbar_inflight_requests` (`api/app/routes/metrics.py:41`) and `rahbar_generation_seconds`. To use it we would have to scrape `/metrics`
with Prometheus and feed it to the HPA through a metrics adapter (Prometheus Adapter or KEDA's Prometheus scaler), with a target
such as 4 in-flight requests per pod. We did not build that. Note also that our resource numbers for the api are still starting guesses
(the manifest comment says so): measured usage is 4m CPU and 66-85Mi memory against a 100m / 192Mi request, so they should be lowered after a load test.

## 4. The indexer's peak memory, our limit, the margin, and the exit code if we get it wrong

The indexer's limit is 1536Mi and its request 512Mi (`k8s/base/indexer-job.yaml:31-32`). The highest reading of `kubectl top pods -n rahbar`, recorded in
`docs/evidence/kubectl-top-indexer.txt`, is 1250Mi, sampled every 10 s during the first full run on all six documents, so the margin is
1536 - 1250 = 286Mi, about 19% of the limit. Setting the limit below the real peak gets the container OOMKilled with exit code 137, and the Job
retries until `backoffLimit: 3` is exhausted and the Job shows `Failed`. A 10-second sampling can miss a short spike, and the Tesseract OCR pass on the scanned errata
is the likeliest one, so the margin is thinner than it looks; we kept the limit rather than lower it. The peak was measured before the heading-detection change, so re-check it
with `grep indexer docs/evidence/kubectl-top-indexer.txt | awk '{print $3}' | sort -n | tail -1` after the final re-index.

## 5. recall@5 by question type: where is it worst, why, and which technique helps?

Exact-term questions are the weakest. Final numbers by type: **[from results.json]**. In our inspection run before the final
re-index (`eval/inspect_golden.py`), the Plate Armor question had a chunk matching the golden "Armor" section at ranks 3 and 5 of the top 5, but rank 3 was
"Armor of Invulnerability", a magic item that only counts because section matching is by prefix (`eval/run_eval.py`, `section_matches`); the real Armor table was at rank 5.
The Half Plate question had it only at rank 5, and the model then answered `answered_from_context=False` because the price was not in the chunks it was shown. The definitional questions
(Death Saving Throws, Long Rest, Dodge, Prone) put the right section first, with top-1 scores of 0.75-0.87, while the correct Armor chunk scored only 0.68 and 0.61.

Why: an embedding captures what a passage is about, not the exact characters in it. "Plate Armor, 1,500 GP, Strength 15" sits inside a table next to
other armors and items with near-identical wording ("Plate Armor of Etherealness", "Dwarven Plate", "Armor of Invulnerability" all ranked above or beside it), so
the vector is close to all of them and nothing rewards the literal token "Plate". The technique from the RAG lecture that addresses this is hybrid
retrieval: a keyword (BM25) score fused with the vector score, so an exact clause number, price or code matches by its characters. We did not implement it.

## 6. EMBED_MODEL changed in the ConfigMap and only the API restarted

The api compares the model name the indexer wrote into the collection metadata (`indexer/pipeline/store.py:30-37`) with its own
`EMBED_MODEL` (`k8s/base/configmap.yaml:17`) on every readiness probe (`api/app/readiness.py:28-32`, `:65-70`). On a mismatch it sets
`embedding_pin: mismatch`, returns 503 naming both models, and the restarted pod stays at `0/1`. Because the rollout uses
`maxUnavailable: 0` (`k8s/base/api-deployment.yaml:20`), the old pods keep serving, so users see nothing while the new pod is held back; the log line names the conflict.
Without the guardrail the new pod would embed questions with a different model than the one that built the index. If the dimensions differ, Chroma errors on
every query; if they happen to match (many models are 768-dimensional like ours), nothing errors at all: retrieval returns the nearest vectors in a space where
"nearest" means nothing, the model answers confidently from irrelevant passages, and no metric changes except answer quality. The demonstration output belongs in
`docs/evidence/embed-pin-mismatch.txt` (`scripts/collect-evidence.sh pin-demo`).

## 7. The failure that cost us the most: the cluster could not reach Ollama

**Symptom.** The indexer Job extracted and chunked all six documents (2,277 chunks), then died with
`RuntimeError: embedding request to http://host.minikube.internal:11434/api/embed failed after 3 attempts: ConnectError` and exit code 1. We re-ran it, and a pod deleted
by hand also counted as a failure, so the Job reached `BackoffLimitExceeded` with no pod at all.

**What we wrongly believed.** First, that `host.minikube.internal` meant "our computer". We installed Ollama on Windows, set `OLLAMA_HOST=0.0.0.0` with `setx`, and
checked the address with `minikube ssh "grep host.minikube.internal /etc/hosts"` (it printed 192.168.49.1, matching our NetworkPolicy). The test
`minikube ssh "curl -sS -m 5 http://host.minikube.internal:11434/api/tags"` failed at once with `Failed to connect ... after 0 ms` (curl exit 7). Second, that the problem was Ollama listening on
localhost only, so we installed Ollama inside WSL Ubuntu and confirmed `ss -ltn | grep 11434` showed `*:11434`. The same curl failed again.

**What told us the truth.** The 0 ms failure meant nothing was routable at that address, not a slow service or a firewall timeout, and the all-interfaces listener proved Ollama was not the
problem. 192.168.49.1 is the gateway of the Docker network that minikube's node lives in on Docker Desktop, which is a different network namespace from both Windows and Ubuntu, so a process
bound on either of them is simply not at that address. The fix was to run Ollama as a Docker container on the minikube network with a fixed IP
(`docker run -d --name ollama --network minikube --ip 192.168.49.10 -v ollama-models:/root/.ollama ollama/ollama`), then change `OLLAMA_URL`
(`k8s/base/configmap.yaml`) and the two egress `ipBlock` rules (`k8s/base/networkpolicy.yaml:75`, `:90`) to that address. The check that proved it:
`minikube ssh "curl -sS -m 5 http://192.168.49.10:11434/api/tags"` listing `nomic-embed-text`. The next index run finished in 2,180.7 s. The cost was hours, not minutes.

Other problems that each cost time, in short: Chroma crash-looped because the Service named `chroma` injected `CHROMA_PORT=tcp://10.108.254.231:8000`, which Chroma parses as its own `u16` port setting
(`kubectl logs chroma-0 --previous`; fixed by `enableServiceLinks: false`, `k8s/base/chroma-statefulset.yaml:27`); every answer was the safe fallback because Groq had retired
`llama-3.1-8b-instant` (the api log said `provider failed ... HTTP 404`); and the SRD 5.1 "Exhaustion" heading was missed, covered in `docs/FAILURE-ANALYSIS.md`.
