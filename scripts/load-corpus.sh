#!/usr/bin/env bash
# Copy documents into the corpus-data PVC so the indexer Job can read them at /corpus.
# usage: scripts/load-corpus.sh corpus/raw      (or eval/fixtures)
set -euo pipefail
SRC="${1:?usage: load-corpus.sh <dir>}"; NS="${NS:-rahbar}"
kubectl -n "$NS" delete pod corpus-loader --ignore-not-found >/dev/null
kubectl -n "$NS" apply -f - <<YAML
apiVersion: v1
kind: Pod
metadata: {name: corpus-loader, namespace: $NS}
spec:
  restartPolicy: Never
  containers:
    - name: loader
      image: busybox:1.36.1
      command: ["sleep", "600"]
      volumeMounts: [{name: corpus, mountPath: /corpus}]
  volumes: [{name: corpus, persistentVolumeClaim: {claimName: corpus-data}}]
YAML
kubectl -n "$NS" wait --for=condition=Ready pod/corpus-loader --timeout=120s
kubectl -n "$NS" cp "$SRC/." corpus-loader:/corpus
kubectl -n "$NS" exec corpus-loader -- ls -la /corpus
kubectl -n "$NS" delete pod corpus-loader --wait=false
