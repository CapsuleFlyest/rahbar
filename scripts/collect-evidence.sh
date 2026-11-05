#!/usr/bin/env bash
# Capture the terminal evidence the handout asks for into docs/evidence/ (timestamped text files).
#   scripts/collect-evidence.sh endpoints | hpa | top | delete-pod | pin-demo | rollout <image> | safe
# `safe` = endpoints + hpa + top. delete-pod needs the Ingress reachable: run `minikube tunnel` in another
# terminal and keep BASE=http://127.0.0.1 (default), or set BASE=http://$(minikube ip).
# Screenshots you must take yourself: branch protection, the blocked merge (grey button) and the green one.
set -uo pipefail
NS="${NS:-rahbar}"; BASE="${BASE:-http://127.0.0.1}"; OUT=docs/evidence; mkdir -p "$OUT"
API_SEL=app.kubernetes.io/name=api
stamp() { echo "# $1 - $(date '+%F %T')"; }
to() { local f="$OUT/$1.txt"; shift; { stamp "$*"; "$@"; } 2>&1 | tee "$f"; echo "-> $f"; }

endpoints() { kubectl -n "$NS" get endpoints api -o wide; kubectl -n "$NS" get pods -l $API_SEL -o wide; }
hpa()       { kubectl -n "$NS" get hpa; kubectl -n "$NS" describe hpa | sed -n '1,30p'; }
top()       { kubectl -n "$NS" top pods; }
delete_pod() {
  local q='{"question":"What DC does the Hide action need?"}'
  hit() { curl -s -m 20 -o /dev/null -w "%{http_code} " -H "Host: rahbar.local" -H 'Content-Type: application/json' -d "$q" "$BASE/api/ask"; }
  echo "warm-up request (fills the cache so the loop costs no Groq calls):"; hit; echo
  local victim; victim=$(kubectl -n "$NS" get pods -l $API_SEL -o jsonpath='{.items[0].metadata.name}')
  echo "deleting $victim; one request per second for 30 s (200 = served, 000 = no answer):"
  kubectl -n "$NS" delete pod "$victim" --wait=false
  for _ in $(seq 1 30); do hit; sleep 1; done; echo
  kubectl -n "$NS" get pods -l $API_SEL
}
pin_demo() {
  echo "Setting EMBED_MODEL to a wrong value in the ConfigMap and restarting the api (old pods keep serving: maxUnavailable 0)"
  kubectl -n "$NS" patch configmap rahbar-config --type merge -p '{"data":{"EMBED_MODEL":"nomic-embed-text-WRONG"}}'
  kubectl -n "$NS" rollout restart deployment/api; sleep 75
  kubectl -n "$NS" get pods -l $API_SEL
  local fresh; fresh=$(kubectl -n "$NS" get pods -l $API_SEL --sort-by=.metadata.creationTimestamp -o name | tail -1)
  echo "--- log of the newest pod ($fresh), conflict lines:"
  kubectl -n "$NS" logs "$fresh" --tail=200 | grep -i "EMBED_MODEL" | tail -3
  echo "--- restoring the ConfigMap from the repo"
  kubectl apply -k k8s/overlays/dev >/dev/null
  kubectl -n "$NS" rollout restart deployment/api
  kubectl -n "$NS" rollout status deployment/api --timeout=300s
  kubectl -n "$NS" get pods -l $API_SEL
}
rollout_demo() {  # $1 = a NEW image tag already loaded into minikube, e.g. rahbar-ui:v2
  local img="${1:?usage: rollout <image:tag>, loaded with: minikube image load <image:tag>}" dep="${DEP:-ui}"
  echo "before:"; kubectl -n "$NS" get deploy "$dep" -o wide
  kubectl -n "$NS" set image "deployment/$dep" "*=$img"
  kubectl -n "$NS" rollout status "deployment/$dep" --timeout=180s
  echo "after the change:"; kubectl -n "$NS" get deploy "$dep" -o wide
  kubectl -n "$NS" rollout history "deployment/$dep"
  kubectl -n "$NS" rollout undo "deployment/$dep"
  kubectl -n "$NS" rollout status "deployment/$dep" --timeout=180s
  echo "after rollout undo (previous version serving again):"; kubectl -n "$NS" get deploy "$dep" -o wide
}

case "${1:-}" in
  endpoints) to endpoints endpoints ;;
  hpa)       to hpa hpa ;;
  top)       to kubectl-top-pods top ;;
  delete-pod) to delete-pod-demo delete_pod ;;
  pin-demo)  to embed-pin-mismatch pin_demo ;;
  rollout)   shift; to rollout-undo rollout_demo "$@" ;;
  safe)      to endpoints endpoints; to hpa hpa; to kubectl-top-pods top ;;
  *) sed -n 2,7p "$0"; exit 2 ;;
esac
