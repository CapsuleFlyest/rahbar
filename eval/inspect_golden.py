#!/usr/bin/env python3
"""What did each golden question retrieve, and where should the relevance floor sit?

Run from the repo root, with the stack up and the index finished:

    .venv/bin/python eval/inspect_golden.py --api http://127.0.0.1:8080 --host rahbar.local --delay 4

Read-only: it writes nothing and changes no file.
"""
import argparse
import sys
import textwrap
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import _norm, ask, load_golden, section_matches  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--host")
    ap.add_argument("--golden", type=Path, default=Path(__file__).resolve().parent / "golden.yaml")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds between questions (rate limits)")
    args = ap.parse_args()

    questions = load_golden(args.golden)
    headers = {"Host": args.host} if args.host else {}
    top_abstain: list[tuple[str, float]] = []
    top_answer: list[tuple[str, float]] = []
    misses: list[str] = []
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for i, q in enumerate(questions):
            if i and args.delay:
                time.sleep(args.delay)
            r = ask(client, args.api, q["question"])
            ret = r.get("retrieved") or []
            rel = q.get("relevant") or []
            print(f"\n{q['id']}  [{q.get('type', 'ordinary')}]  {q['question']}")
            for w in rel:
                print(f"   want  {w['source']} | {w['section']}")
            for rank, p in enumerate(ret[:5], 1):
                hit = any(w["source"].lower() == str(p.get("source", "")).lower()
                          and section_matches(p.get("section", ""), w["section"]) for w in rel)
                print(f"   {rank} {'✓' if hit else ' '} {p.get('score', 0):.3f}  {p.get('source')} | {p.get('section')}  (p.{p.get('page')})")
            print(f"   -> answered_from_context={r.get('answered_from_context')}  "
                  f"confidence={r.get('confidence')}  fallback={r.get('fallback', False)}")
            expect = q.get("expect")
            if expect:
                found = _norm(expect) in _norm(r.get("answer"))
                print(f"   expect  \"{expect}\"  {'FOUND in answer' if found else 'NOT in answer (check the wording)'}")
            print(textwrap.fill(str(r.get("answer") or "").strip(), width=100,
                                initial_indent="   ANSWER  ", subsequent_indent="           "))
            for c in r.get("citations") or []:
                print(f"   cited   {c.get('source')} | {c.get('section')}  (p.{c.get('page')})")
            top1 = float(ret[0]["score"]) if ret else 0.0
            if q.get("must_abstain"):
                top_abstain.append((q["id"], top1))
                if r.get("answered_from_context"):
                    misses.append(f"{q['id']}: must abstain but ANSWERED (-10 points)")
            else:
                top_answer.append((q["id"], top1))
                if rel and not any(any(w["source"].lower() == str(p.get("source", "")).lower()
                                       and section_matches(p.get("section", ""), w["section"])
                                       for w in rel) for p in ret[:5]):
                    misses.append(f"{q['id']}: no wanted section in the top 5 "
                                  f"(wrong section name in golden.yaml, or a real retrieval miss)")

    print("\n" + "=" * 72)
    print("top-1 score, must-abstain questions :", [(i, round(s, 3)) for i, s in top_abstain])
    low = min(top_answer, key=lambda t: t[1]) if top_answer else None
    high = max(top_abstain, key=lambda t: t[1]) if top_abstain else None
    if low:
        print(f"lowest top-1 among answerable       : {low[0]} = {low[1]:.3f}")
    if low and high:
        if high[1] < low[1]:
            print(f"a floor between {high[1]:.3f} and {low[1]:.3f} separates them "
                  f"(try {(high[1] + low[1]) / 2:.2f}).")
        else:
            print(f"OVERLAP: {high[0]} scores {high[1]:.3f}, at or above answerable {low[0]} "
                  f"({low[1]:.3f}). The floor alone cannot separate them; "
                  "abstention then relies on the model saying answered_from_context=false.")
    for m in misses:
        print("PROBLEM:", m)
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
