#!/usr/bin/env python3
"""Print a RAHBAR /api/ask reply the way a chatbot would, instead of raw JSON.

    make ask Q="What DC does the Hide action need?"          # readable
    make ask Q="..." RAW=1                                    # the full JSON

Reads the JSON reply on stdin. The question comes from the Q environment variable.
"""
import json
import os
import sys
import textwrap

WIDTH = 92


def wrap(text: str, indent: str = "") -> str:
    return "\n".join(textwrap.fill(line, WIDTH, initial_indent=indent, subsequent_indent=indent)
                     if line.strip() else "" for line in str(text).splitlines())


def main() -> int:
    raw = sys.stdin.read()
    try:
        r = json.loads(raw)
    except ValueError:
        print("No JSON came back, so the API was not reached. Is the Ingress reachable?")
        print("  - port-forward:  kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80")
        print("    then:          make ask INGRESS_IP=127.0.0.1:8080 Q=\"...\"")
        if raw.strip():
            print("\nWhat was received:\n" + raw[:400])
        return 1
    if "answer" not in r:                       # an error body, e.g. a 422 for a bad question
        print(json.dumps(r, indent=2))
        return 1

    question = os.environ.get("Q", "")
    if question:
        print(wrap(f"Q: {question}"))
    print(wrap(f"A: {r['answer']}"))

    cites = r.get("citations") or []
    if cites:
        print("\nSources")
        for i, c in enumerate(cites, 1):
            print(wrap(f"[{i}] {c.get('source')} › {c.get('section')} (p.{c.get('page')})", "  "))
    elif not r.get("answered_from_context"):
        print("\n(No sources: the corpus does not cover this question.)")

    ret = r.get("retrieved") or []
    if ret:
        print("\nRetrieved (top-k, most similar first)")
        for i, p in enumerate(ret, 1):
            print(wrap(f"{i}. {p.get('score', 0):.3f}  {p.get('source')} › {p.get('section')} "
                       f"(p.{p.get('page')})", "  "))

    flags = [f"answered_from_context={r.get('answered_from_context')}",
             f"confidence={r.get('confidence')}", f"cached={r.get('cached')}",
             f"provider={r.get('provider')}"]
    print("\n" + " · ".join(flags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
