#!/usr/bin/env bash
# Commit the repo in small conventional commits and push to the dev branch.
# Run from the repo root:  bash scripts/push-commits.sh
# Safe to re-run: groups with nothing new to commit are skipped.
set -euo pipefail

REMOTE_URL="${REMOTE_URL:-https://github.com/CapsuleFlyer/rahbar.git}"
BRANCH="${BRANCH:-dev}"

[ -f scripts/check_submission.py ] || { echo "run this from the repo root"; exit 1; }
[ -d .git ] || git init -q
git config user.name "CapsuleFlyer"
git config user.email "shaheerawan28@gmail.com"
git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE_URL"
git checkout -q "$BRANCH" 2>/dev/null || git checkout -q -b "$BRANCH"

# Never commit secrets or downloaded documents (.gitignore also covers these).
if git ls-files --others --exclude-standard | grep -E '(^|/)\.env|secret[^/]*\.ya?ml$|kubeconfig|corpus/raw/' \
   | grep -v placeholder; then
  echo "refusing: secret-looking or raw corpus files are not ignored"; exit 1
fi

commit() {  # commit "<message>" <paths...>
  local msg="$1"; shift
  local paths=()
  for p in "$@"; do [ -e "$p" ] && paths+=("$p"); done
  [ ${#paths[@]} -gt 0 ] || return 0
  git add -- "${paths[@]}"
  if git diff --cached --quiet; then echo "skip (nothing new): $msg"; else git commit -q -m "$msg"; echo "done: $msg"; fi
}

commit "chore: add rahbar starter kit" \
  STARTER.md .gitignore ui/index.html ui/nginx.conf scripts/check_submission.py \
  corpus/fetch.py corpus/sources.example.yaml eval/golden.example.yaml eval/fixtures
commit "feat(indexer): implement extract, clean, chunk, embed and store stages" indexer \
  corpus/sources.yaml
commit "feat(api): add grounded retrieval, cache, readiness and providers" api/app api/tests \
  api/requirements.txt api/requirements-dev.txt api/pyproject.toml
commit "feat(eval): implement recall, citation validity and abstention gate" \
  eval/run_eval.py eval/golden.yaml
commit "feat(k8s): add base manifests and dev, prod and ci overlays" k8s
commit "build: add Dockerfiles and dockerignore files" api/Dockerfile api/.dockerignore \
  indexer/Dockerfile indexer/.dockerignore ui/Dockerfile ui/.dockerignore
commit "ci: add ci and cd workflows, helper scripts and make targets" .github scripts/ci \
  scripts/load-corpus.sh Makefile
commit "docs: add README, ADR drafts, architecture notes and AI usage" README.md docs \
  MANUAL-STEPS.md
commit "chore: add remaining files" scripts/push-commits.sh .

git push -u origin "$BRANCH"
echo "pushed to $BRANCH. Open a PR dev -> main on GitHub and name the corpus in it."