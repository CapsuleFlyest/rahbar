# Architecture notes

Chroma is a **StatefulSet**, not a Deployment: it needs a stable identity and its own PVC per replica
(`volumeClaimTemplates` in `k8s/base/chroma-statefulset.yaml`), and two pods must never write one volume.
The indexer Job is the only writer; the api only reads (ADR 0001). Redis is a Deployment with a PVC
because the cache is disposable and a single replica is enough.
