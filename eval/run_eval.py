#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

Exit codes: 0 every gate passed, 1 a gate failed, 2 not ready (unfinished golden set).
recall@k matches retrieved passages to golden ones by (source, section): see section_matches.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    unfinished = [q.get("id", "?") for q in questions
                  if not q.get("must_abstain") and not (q.get("relevant") or [])]
    if unfinished:
        print(f"golden set is unfinished: {len(unfinished)} question(s) have no `relevant` "
              f"passages: {', '.join(map(str, unfinished))}.\n"
              f"Read the documents and fill `relevant` (source + section) before scoring.")
        sys.exit(2)
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _norm(text: object) -> str:
    return " ".join(str(text or "").split()).lower()


def section_matches(retrieved_section: str, relevant_section: str) -> bool:
    """Equal, or the retrieved section starts with the relevant one followed by a space, ':'
    or '-'. So "5.4" matches "5.4 Academic Warning" but not "5.41 Fees"."""
    got, want = _norm(retrieved_section), _norm(relevant_section)
    if not want:
        return False
    if got == want:
        return True
    return got.startswith(want) and got[len(want)] in " :-"


def _pair_matches(relevant: dict, ref: dict) -> bool:
    return (_norm(relevant.get("source")) == _norm(ref.get("source"))
            and section_matches(ref.get("section", ""), relevant.get("section", "")))


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Each relevant pair counts once, however many chunks of it were retrieved. Matching is by
    source (case-insensitive) and section (see section_matches). Return None when the
    question has no relevant passages (must-abstain questions)."""
    if not relevant:
        return None
    top = retrieved[:k]
    found = sum(1 for rel in relevant if any(_pair_matches(rel, ref) for ref in top))
    return found / len(relevant)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    citations = response.get("citations") or []
    if not citations:
        return None
    retrieved = response.get("retrieved") or []
    valid = sum(1 for c in citations
                if any(_norm(c.get("source")) == _norm(r.get("source"))
                       and _norm(c.get("section")) == _norm(r.get("section"))
                       for r in retrieved))
    return valid / len(citations)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    r3: dict[str, list[float]] = {}
    r5: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    cited = valid = 0
    abstain_total = abstain_ok = 0
    expect_total = expect_hit = 0
    for row in rows:
        qtype = row.get("type", "ordinary")
        counts[qtype] = counts.get(qtype, 0) + 1
        response = row["response"]
        retrieved = response.get("retrieved") or []
        a3 = recall_at_k(row.get("relevant") or [], retrieved, 3)
        a5 = recall_at_k(row.get("relevant") or [], retrieved, 5)
        if a3 is not None and a5 is not None:
            r3.setdefault(qtype, []).append(a3)
            r5.setdefault(qtype, []).append(a5)
        citations = response.get("citations") or []
        validity = citation_validity(response)
        if validity is not None:
            cited += len(citations)
            valid += round(validity * len(citations))
        if row.get("must_abstain"):
            abstain_total += 1
            abstain_ok += 0 if response.get("answered_from_context") else 1
        if row.get("expect") and response.get("answered_from_context"):
            expect_total += 1
            expect_hit += 1 if _norm(row["expect"]) in _norm(response.get("answer")) else 0
    all3 = [v for values in r3.values() for v in values]
    all5 = [v for values in r5.values() for v in values]
    return {
        "recall_at_3": _mean(all3),
        "recall_at_5": _mean(all5),
        "recall_at_3_by_type": {t: _mean(v) for t, v in sorted(r3.items())},
        "recall_at_5_by_type": {t: _mean(v) for t, v in sorted(r5.items())},
        "citation_validity": round(valid / cited, 4) if cited else None,
        "citations_checked": cited,
        "abstention_correctness": round(abstain_ok / abstain_total, 4) if abstain_total else None,
        "must_abstain_questions": abstain_total,
        "expect_hit_rate": round(expect_hit / expect_total, 4) if expect_total else None,
        "questions_by_type": dict(sorted(counts.items())),
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures: list[str] = []
    recall5 = results.get("recall_at_5")
    if baseline is not None and baseline.get("recall_at_5") is not None:
        floor = baseline["recall_at_5"] - MAX_RECALL5_DROP
        if recall5 is None or recall5 < floor:
            failures.append(
                f"recall@5 {recall5} is more than {MAX_RECALL5_DROP:.0%} below the baseline "
                f"{baseline['recall_at_5']} (minimum {floor:.4f})")
    abstention = results.get("abstention_correctness")
    if abstention is not None and abstention < REQUIRED_ABSTENTION:
        failures.append(f"abstention correctness {abstention:.0%}: a must-abstain question "
                        f"was answered from context (required {REQUIRED_ABSTENTION:.0%})")
    validity = results.get("citation_validity")
    if validity is not None and validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity {validity:.0%} is below {MIN_CITATION_VALIDITY:.0%}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    results = summarise(rows)
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    failures = gate(results, baseline)

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
