"""The precision/recall gate over the real labelled set: tests/labelled/messages.jsonl.

The set is meant to be honest — a test of accountscope/classify.py and
accountscope/facts.py, not a mirror of their keyword tables — so it deliberately
includes hard cases (keyword collisions, translated subjects, masked/unmasked/
malformed facts, near-miss negatives). Some predictions are expected to be wrong;
that is what turns these numbers into a real measurement instead of a tautology.

Run with `-s` to see the printed precision/recall tables:
    .venv/bin/python -m pytest tests/test_precision.py -s
"""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

from accountscope.classify import classify
from accountscope.facts import extract_facts

LABELLED = Path(__file__).parent / "labelled" / "messages.jsonl"
LINT_SCRIPT = Path(__file__).parent.parent / "scripts" / "lint_labelled.py"

TYPES = ["otp", "verify", "reset", "signup", "receipt", "statement", "notice", "marketing", "other"]
FACT_TYPES = ["card", "phone", "address"]

# Named gate thresholds (spelled out here, not inlined, so a future change to any one
# of them shows up as a one-line diff).
TYPE_PRECISION_THRESHOLD = 0.70
TYPE_RECALL_THRESHOLD = 0.60
FACT_PRECISION_THRESHOLD = 0.70
FACT_RECALL_THRESHOLD = 0.60
MIN_TOTAL_ROWS = 300
MIN_ROWS_PER_TYPE = 25
MIN_FACTS_PER_TYPE = 15


def load_rows() -> list[dict]:
    return [json.loads(line) for line in LABELLED.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_type_precision_per_type():
    rows = load_rows()
    assert len(rows) >= MIN_TOTAL_ROWS, f"labelled set has {len(rows)} rows, need >= {MIN_TOTAL_ROWS}"

    predicted_count: Counter = Counter()
    true_count: Counter = Counter()
    correct_count: Counter = Counter()
    for row in rows:
        predicted = classify(row["subject"], row["list_unsubscribe"])
        true_type = row["type"]
        predicted_count[predicted] += 1
        true_count[true_type] += 1
        if predicted == true_type:
            correct_count[true_type] += 1

    print(f"\n{'type':<12}{'rows':>6}{'precision':>12}{'recall':>10}")
    failures = []
    for t in TYPES:
        rows_t = true_count[t]
        precision = correct_count[t] / predicted_count[t] if predicted_count[t] else 0.0
        recall = correct_count[t] / rows_t if rows_t else 0.0
        print(f"{t:<12}{rows_t:>6}{precision:>12.2%}{recall:>10.2%}")
        if rows_t < MIN_ROWS_PER_TYPE:
            failures.append(f"{t}: only {rows_t} labelled rows, need >= {MIN_ROWS_PER_TYPE}")
        if precision < TYPE_PRECISION_THRESHOLD:
            failures.append(f"{t}: precision {precision:.2%} < threshold {TYPE_PRECISION_THRESHOLD:.0%}")
        if recall < TYPE_RECALL_THRESHOLD:
            failures.append(f"{t}: recall {recall:.2%} < threshold {TYPE_RECALL_THRESHOLD:.0%}")
    assert not failures, "\n".join(failures)


def test_fact_precision_per_type():
    rows = load_rows()

    predicted_count: Counter = Counter()
    labelled_count: Counter = Counter()
    correct_count: Counter = Counter()
    for row in rows:
        expected = {(f["fact"], f["value"]) for f in row["facts"]}
        got = {(h.fact, h.value) for h in extract_facts(row["body"], "2024-01-01")}
        for ft in FACT_TYPES:
            expected_ft = {pair for pair in expected if pair[0] == ft}
            got_ft = {pair for pair in got if pair[0] == ft}
            predicted_count[ft] += len(got_ft)
            labelled_count[ft] += len(expected_ft)
            correct_count[ft] += len(expected_ft & got_ft)

    print(f"\n{'fact':<10}{'labelled':>10}{'precision':>12}{'recall':>10}")
    failures = []
    for ft in FACT_TYPES:
        precision = correct_count[ft] / predicted_count[ft] if predicted_count[ft] else 0.0
        recall = correct_count[ft] / labelled_count[ft] if labelled_count[ft] else 0.0
        print(f"{ft:<10}{labelled_count[ft]:>10}{precision:>12.2%}{recall:>10.2%}")
        if labelled_count[ft] < MIN_FACTS_PER_TYPE:
            failures.append(f"{ft}: only {labelled_count[ft]} labelled facts, need >= {MIN_FACTS_PER_TYPE}")
        if precision < FACT_PRECISION_THRESHOLD:
            failures.append(f"{ft}: precision {precision:.2%} < threshold {FACT_PRECISION_THRESHOLD:.0%}")
        if recall < FACT_RECALL_THRESHOLD:
            failures.append(f"{ft}: recall {recall:.2%} < threshold {FACT_RECALL_THRESHOLD:.0%}")
    assert not failures, "\n".join(failures)


def _load_lint_module():
    """Import scripts/lint_labelled.py the way tests/test_refresh_data.py imports
    scripts/refresh_data.py: scripts/ is not a package, so via its file location."""
    spec = importlib.util.spec_from_file_location("lint_labelled", LINT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_labelled_file_passes_lint():
    lint = _load_lint_module()
    errors = lint.check(LABELLED)
    assert errors == [], "\n".join(errors)


def test_lint_catches_bad_rows(tmp_path):
    lint = _load_lint_module()
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        "\n".join(
            [
                "not json at all",
                json.dumps({"subject": "x", "list_unsubscribe": False, "body": "y",
                            "type": "not-a-type", "facts": []}),
                json.dumps({"subject": "x", "list_unsubscribe": False, "body": "y",
                            "type": "other", "facts": [{"fact": "ssn", "value": "1"}]}),
                json.dumps({"subject": "Contact me at person@gmail.com", "list_unsubscribe": False,
                            "body": "y", "type": "other", "facts": []}),
                json.dumps({"subject": "ok", "list_unsubscribe": False, "body": "y", "type": "other"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    errors = lint.check(bad)
    assert len(errors) >= 5


def test_lint_allows_example_domains_and_at_sign_in_calendar_subjects(tmp_path):
    lint = _load_lint_module()
    good = tmp_path / "good.jsonl"
    good.write_text(
        "\n".join(
            [
                json.dumps({"subject": "Invitation: Team sync @ Thu Oct 2, 2026 3pm", "list_unsubscribe": False,
                            "body": "Order confirmed at store.example, receipt sent to me@example.com.",
                            "type": "other", "facts": []}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert lint.check(good) == []


def test_known_bad_labels_stay_corrected():
    """Three rows whose labels were wrong on review. Pinned so a later edit of the
    labelled file cannot quietly put them back.

    - "Please verify your shipping address ..." asks the reader to verify something, so
      it is `verify`, not a receipt that happens to mention an order.
    - "We've verified your delivery slot ..." reports a delivery arrangement, so it is
      `notice`; nothing is being receipted and nothing is asked of the reader.
    - "Sydney NSW 3000" is not an address: 3000 is Melbourne, Sydney's CBD is 2000.
    """
    by_subject = {row["subject"]: row for row in load_rows()}

    assert by_subject["Please verify your shipping address for order #5521"]["type"] == "verify"
    assert by_subject["We've verified your delivery slot for order #7789"]["type"] == "notice"

    sydney = by_subject["Your package is on its way from Northwind Traders"]
    assert "Sydney NSW 2000" in sydney["body"] and "NSW 3000" not in sydney["body"]
    assert sydney["facts"] == [{"fact": "address", "value": "Sydney NSW 2000"}]
