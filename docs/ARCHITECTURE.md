# Architecture notes

Chroma is a **StatefulSet**, not a Deployment: it needs a stable identity and its own PVC per replica
(`volumeClaimTemplates` in `k8s/base/chroma-statefulset.yaml`), and two pods must never write one volume.
The indexer Job is the only writer; the api only reads (ADR 0001). Redis is a Deployment with a PVC
because the cache is disposable and a single replica is enough.

## How a question flows
`ui` (nginx) and `api` sit behind one Ingress (`/` and `/api`). The api checks the Redis cache, embeds the question,
reads the top-k chunks from Chroma (superseded documents filtered out unless the question asks for an older
version), builds a prompt with delimited evidence, asks the LLM for JSON that matches the `Answer` schema, validates it
(one retry, then a safe fallback) and drops any citation that was not retrieved. Only the indexer Job writes to Chroma.

## Two services outside the cluster, and why
- **Groq** generates answers. Our laptops cannot run a useful chat model next to minikube (ADR 0004).
- **Ollama** only embeds (`nomic-embed-text`). It runs as a Docker container on the minikube network at `192.168.49.10`:
  the `host.minikube.internal` gateway could not reach an Ollama installed on Windows or in WSL. The address appears in
  `OLLAMA_URL` (ConfigMap) and in the api and indexer egress rules (NetworkPolicy), and the three must agree.

## Decisions worth knowing
- `chroma-statefulset.yaml:2` gives Chroma its own PVC; `chroma-statefulset.yaml:27` turns off service links, because the Service named `chroma` otherwise injects `CHROMA_PORT=tcp://...`, which Chroma parses as its port and panics.
- The embedding model is pinned once (`EMBED_MODEL` in the ConfigMap), written into the collection metadata by the indexer and checked by `/readyz` (ADR 0001, section 4.4 of the handout).
