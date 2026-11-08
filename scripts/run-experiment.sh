#!/usr/bin/env bash
# One measured experiment against the live cluster: change ConfigMap settings, re-index when chunking
# changed, restart the api, flush the cache, run the golden set and save the numbers.
#
#   scripts/run-experiment.sh run <name> [KEY=VALUE ...]     e.g. run chunk-200-25 CHUNK_SIZE=200 CHUNK_OVERLAP=25
#   scripts/run-experiment.sh restore [--reindex]            put the repo's settings back (--reindex after chunking runs)
#
# Allowed keys: CHUNK_STRATEGY CHUNK_SIZE CHUNK_OVERLAP TOP_K TEMPERATURE RELEVANCE_FLOOR CACHE_THRESHOLD.
# Any CHUNK_* key re-indexes (a Job made from cronjob/reindex, never by hand-deleting pods). With no keys the
# script just restarts the api and evaluates, which is what you want after rebuilding the api image.
# Results: eval/experiments/<name>.json plus a summary on screen. Needs: kubectl, the repo .venv (make install),
# python3. Groq is slow on the free tier: DELAY (seconds between questions, default 5) can be raised.
set -uo pipefail
NS="${NS:-rahbar}"; CM=rahbar-config; PY="${PY:-.venv/bin/python}"; DELAY="${DELAY:-5}"
ALLOWED=" CHUNK_STRATEGY CHUNK_SIZE CHUNK_OVERLAP TOP_K TEMPERATURE RELEVANCE_FLOOR CACHE_THRESHOLD "

die() { echo "error: $*" >&2; exit 1; }
reindex() {  # $1 = job name; waits for it and prints the indexer's own summary line
  kubectl -n "$NS" create job "$1" --from=cronjob/reindex || die "could not create job $1"
  echo "re-indexing as job/$1 (minutes on GPU Ollama, about 35 on CPU)..."
  kubectl -n "$NS" wait --for=condition=complete "job/$1" --timeout=3h || {
    kubectl -n "$NS" logs "job/$1" --tail=30; die "job $1 did not complete"; }
  kubectl -n "$NS" logs "job/$1" | grep '"msg": "embedded"' | tail -1
}

case "${1:-}" in
  restore)
    kubectl apply -k k8s/overlays/dev || die "apply failed"
    [ "${2:-}" = "--reindex" ] && reindex "restore-$(date +%H%M%S)"
    kubectl -n "$NS" rollout restart deployment/api
    kubectl -n "$NS" rollout status deployment/api --timeout=300s
    echo "restored. Re-index (restore --reindex) if the last experiment changed CHUNK_* settings."
    ;;
  run)
    name="${2:?usage: run <name> [KEY=VALUE ...]}"; shift 2
    [[ "$name" =~ ^[a-z0-9-]+$ ]] || die "name must be lowercase letters, digits and dashes"
    need_reindex=0
    for kv in "$@"; do
      key="${kv%%=*}"; [[ "$kv" == *=* ]] || die "bad setting '$kv' (use KEY=VALUE)"
      [[ "$ALLOWED" == *" $key "* ]] || die "key $key not allowed (allowed:$ALLOWED)"
      [[ "$key" == CHUNK_* ]] && need_reindex=1
    done
    if [ "$#" -gt 0 ]; then
      patch=$(python3 -c 'import json,sys;print(json.dumps({"data":dict(a.split("=",1) for a in sys.argv[1:])}))' "$@")
      kubectl -n "$NS" patch configmap "$CM" --type merge -p "$patch" || die "patch failed"
    fi
    chunks_line=""
    [ "$need_reindex" = 1 ] && chunks_line=$(reindex "exp-$name-$(date +%H%M%S)")
    kubectl -n "$NS" rollout restart deployment/api
    kubectl -n "$NS" rollout status deployment/api --timeout=300s || die "api did not become ready"
    kubectl -n "$NS" exec deploy/redis -- redis-cli FLUSHALL >/dev/null || echo "warning: could not flush the cache"
    mkdir -p eval/experiments
    kubectl -n "$NS" port-forward svc/api 18000:8000 >/dev/null 2>&1 & pf=$!
    trap 'kill $pf 2>/dev/null' EXIT; sleep 3
    "$PY" eval/run_eval.py --api http://localhost:18000 --delay "$DELAY" --out "eval/experiments/$name.json"
    echo; echo "=== $name ($*) ==="; [ -n "$chunks_line" ] && echo "indexer: $chunks_line"
    "$PY" - "$name" <<'PYEOF'
import json, sys
r = json.load(open(f"eval/experiments/{sys.argv[1]}.json"))
for k in ("recall_at_3", "recall_at_5", "citation_validity", "abstention_correctness", "fallback_answers"):
    print(f"{k:24} {r.get(k)}")
print("recall@5 by type:", r.get("recall_at_5_by_type"))
PYEOF
    echo "Remember: scripts/run-experiment.sh restore [--reindex] when you are done."
    ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
