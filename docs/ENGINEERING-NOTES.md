# Engineering notes

<!-- STARTER-TODO(7): write your own answer under each question. The pointer sheets give the files and line numbers
     to cite; the answer, the reasoning and question 7 must be yours. A generic answer scores zero. Delete this when done. -->

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?
**Pointers:** replicas `k8s/base/api-deployment.yaml:10`; Chroma's own PVC `k8s/base/chroma-statefulset.yaml:2`; the indexer is a Job with `restartPolicy: OnFailure` `k8s/base/indexer-job.yaml:15` and `backoffLimit` `k8s/base/indexer-job.yaml:10`; upsert-then-prune so the collection is never empty (`indexer/pipeline/store.py:71`); `/readyz` rejects an empty collection (`api/app/readiness.py:60`).
**Your answer:** name the failure (three writers on one volume, every restart re-indexes, readiness lies, no re-index without a redeploy), the object that prevents it, and the line.

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?
**Pointers:** liveness `k8s/base/api-deployment.yaml:57` uses `/healthz` (touches nothing); readiness `k8s/base/api-deployment.yaml:63` uses `/readyz`, which checks Chroma, the collection, Redis and the pin (`api/app/readiness.py:28`).
**Your answer:** with liveness depending on Chroma, what does the kubelet do to all three pods, and why does a slow dependency become an outage?

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?
**Pointers:** HPA target `k8s/base/hpa.yaml:13` (70% of the CPU request, `cpu: 100m` at `k8s/base/api-deployment.yaml:74`); the api already exports an in-flight gauge (`api/app/routes/metrics.py:39`); run `kubectl get hpa -n rahbar` while a question is generating and note the CPU figure.
**Your answer:** the pod waits on Groq (I/O), so CPU stays low; which signal should scale it (in-flight requests or queue depth) and what you would have to build (a custom or external metrics adapter such as KEDA or Prometheus Adapter).

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong
**Pointers:** limit 1536Mi, request 512Mi (`k8s/base/indexer-job.yaml:32`); peak 1250Mi in `docs/evidence/kubectl-top-indexer.txt` (first full run on all six documents; re-check if you re-index after the heading fix: `grep indexer docs/evidence/kubectl-top-indexer.txt | awk '{print $3}' | sort -n | tail -1`).
**Your answer:** margin is 1536 - 1250 = 286Mi (about 19%); wrong limit gives OOMKilled, exit code 137. Say whether the margin is enough and why.

## 5. recall@5 by question type: where is it worst, and why?
**Pointers:** `eval/results.json` (after `python eval/run_eval.py`); matching rule `eval/run_eval.py:98`.
**Your answer:** which type is worst (expect exact-term), why embeddings blur exact terms (clause numbers, GP costs, DCs), and which lecture technique addresses it (hybrid retrieval: keyword plus vector). Quote your own numbers.

## 6. EMBED_MODEL changed on the API only: what does your system do?
**Pointers:** pin in `k8s/base/configmap.yaml:2`; written by `indexer/pipeline/store.py:30`; checked at `api/app/readiness.py:28`; the demo output (pod at 0/1 and the log line naming the conflict) belongs in `docs/evidence/`.
**Your answer:** what the pod does (refuses to become ready, logs both model names) versus what it would have done without the guardrail (retrieval returns nonsense, no error).

## 7. The failure that cost us more than an hour
Write this one yourselves. Real candidates from this project (pick the one that cost you most, and give the symptom, what you wrongly believed, and the exact command or log line that told you the truth):
- Chroma crash-looping: `kubectl logs chroma-0 --previous` showed `found string "tcp://..." expected u16 for key "PORT"` (`chroma-statefulset.yaml:27`).
- The indexer could not embed: `ConnectError` to `host.minikube.internal`; `minikube ssh "curl ..."` failed with exit 7 even though Ollama listened on all interfaces.
- The indexer Job showed `BackoffLimitExceeded` with no pod after a pod was deleted by hand.
- Every answer was the safe fallback; the api log said `provider failed ... HTTP 404` (Groq had retired the model).
