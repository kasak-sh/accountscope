import json
from pathlib import Path

from accountscope.classify import classify
from accountscope.facts import extract_facts

LABELLED = Path(__file__).parent / "labelled" / "messages.jsonl"
THRESHOLD = 0.70


def load():
    return [json.loads(line) for line in LABELLED.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_type_precision_meets_threshold():
    rows = load()
    correct = sum(1 for r in rows if classify(r["subject"], r["list_unsubscribe"]) == r["type"])
    precision = correct / len(rows)
    print(f"\ntype precision: {precision:.2%} ({correct}/{len(rows)})")
    assert precision >= THRESHOLD


def test_fact_precision_meets_threshold():
    rows = load()
    predicted = 0
    correct = 0
    expected_total = 0
    found = 0
    for r in rows:
        expected = {(f["fact"], f["value"]) for f in r["facts"]}
        expected_total += len(expected)
        got = {(h.fact, h.value) for h in extract_facts(r["body"], "2024-01-01")}
        predicted += len(got)
        correct += len(got & expected)
        found += len(got & expected)
    precision = correct / predicted if predicted else 1.0
    recall = found / expected_total if expected_total else 1.0
    print(f"\nfact precision: {precision:.2%} ({correct}/{predicted}); recall: {recall:.2%} ({found}/{expected_total})")
    assert precision >= THRESHOLD
