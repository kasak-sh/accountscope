import csv
import json

import pytest

from accountscope.report import render_summary, write_csv, write_json

DATA = {
    "schema": "accountscope/1",
    "generated_at": "2026-10-02T09:14:00+00:00",
    "source": {"path": "takeout.mbox", "messages": 1000, "skipped": 3, "date_range": ["2014-03-02", "2026-09-30"],
               "personal_senders_skipped": 12},
    "self": [{"address": "me@gmail.com", "aliases": ["me+shop@gmail.com"], "messages": 990, "declared": False}],
    "organisations": [
        {"key": "example.com", "name": "Example Bank", "sender_addresses": ["alerts@example.com"],
         "types": {"otp": 42, "statement": 96, "marketing": 12}, "marketing_only": False,
         "first_seen": "2016-05-11", "last_seen": "2026-09-28",
         "writes_to": [{"address": "me@gmail.com", "last": "2026-09-28", "count": 150}],
         "holds": [{"fact": "card", "value": "ending 4421", "evidence": "e", "seen": "2026-09-01", "confidence": "high", "inferred": False}],
         "delete": {"name": "Example", "url": "https://example.com/close", "difficulty": "hard"},
         "category": "finance", "via_relay": False},
        {"key": "news.example", "name": "Newsletter", "sender_addresses": ["n@news.example"],
         "types": {"marketing": 30}, "marketing_only": True, "first_seen": "2020-01-01", "last_seen": "2026-01-01",
         "writes_to": [{"address": "me@gmail.com", "last": "2026-01-01", "count": 30}],
         "holds": [], "delete": None, "category": "other", "via_relay": False},
    ],
}


def test_write_json_is_atomic_and_round_trips(tmp_path):
    out = tmp_path / "accountscope.json"
    write_json(DATA, out)
    assert json.loads(out.read_text()) == DATA
    assert not (tmp_path / "accountscope.json.tmp").exists()


def test_write_json_failure_leaves_no_partial_target(tmp_path):
    out = tmp_path / "accountscope.json"
    # Test 1: non-serializable data fails without creating target or temp
    with pytest.raises(TypeError):
        write_json({"x": object()}, out)
    assert not out.exists()
    assert not (tmp_path / "accountscope.json.tmp").exists()

    # Test 2: pre-existing good file is untouched by failed rewrite
    write_json({"good": "data"}, out)
    original_content = out.read_text()
    with pytest.raises(TypeError):
        write_json({"x": object()}, out)
    assert out.read_text() == original_content


def test_write_csv_flattens(tmp_path):
    out = tmp_path / "inv.csv"
    write_csv(DATA, out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["key"] == "example.com"
    assert rows[0]["writes_to"] == "me@gmail.com (2026-09-28)"
    assert rows[0]["holds"] == "card ending 4421 [high]"
    assert rows[0]["delete_url"] == "https://example.com/close"
    assert rows[1]["marketing_only"] == "true"


def test_render_summary_mentions_key_facts(tmp_path):
    text = render_summary(DATA, {"skipped": 3, "no_recipients": 0, "body_failures": 1}, [tmp_path / "a.json", tmp_path / "a.html"])
    assert "messages: 1,000" in text
    assert "me@gmail.com" in text and "--me" in text
    assert "finance" in text
    assert "Example Bank" in text
    assert "skipped" in text and "3" in text
    assert "a.json" in text and "a.html" in text


def test_render_summary_reports_personal_senders_skipped(tmp_path):
    text = render_summary(DATA, {"skipped": 3, "no_recipients": 0, "body_failures": 1}, [tmp_path / "a.json"])
    assert "12 personal-mail senders" in text


def test_render_summary_without_the_personal_sender_count(tmp_path):
    data = json.loads(json.dumps(DATA))
    del data["source"]["personal_senders_skipped"]
    text = render_summary(data, {"skipped": 0, "no_recipients": 0, "body_failures": 0}, [tmp_path / "a.json"])
    assert "0 personal-mail senders" in text


def test_write_csv_neutralises_formula_injection(tmp_path):
    data = json.loads(json.dumps(DATA))
    data["organisations"][0]["name"] = "=cmd|'/C calc'!A1"
    data["organisations"][0]["key"] = "+evil.example"
    data["organisations"][1]["name"] = "-2+3"
    data["organisations"][1]["key"] = "@SUM(A1:A9)"
    out = tmp_path / "inv.csv"
    write_csv(data, out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["name"] == "'=cmd|'/C calc'!A1"
    assert rows[0]["key"] == "'+evil.example"
    assert rows[1]["name"] == "'-2+3"
    assert rows[1]["key"] == "'@SUM(A1:A9)"


def test_write_csv_leaves_ordinary_fields_alone(tmp_path):
    out = tmp_path / "inv.csv"
    write_csv(DATA, out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["name"] == "Example Bank"
    assert rows[0]["first_seen"] == "2016-05-11"
    assert rows[0]["delete_url"] == "https://example.com/close"


def with_inferred_fact():
    """DATA plus a second held fact on the bank that the trust table calls inferred."""
    data = json.loads(json.dumps(DATA))
    data["organisations"][0]["holds"].append(
        {"fact": "phone", "value": "ending 9931", "evidence": "e", "seen": "2026-09-02",
         "confidence": "medium", "inferred": True})
    return data


def test_write_csv_flags_inferred_facts(tmp_path):
    out = tmp_path / "inv.csv"
    write_csv(with_inferred_fact(), out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["holds"] == "card ending 4421 [high]; phone ending 9931 [medium] (inferred)"


def test_write_csv_leaves_trusted_facts_unflagged(tmp_path):
    out = tmp_path / "inv.csv"
    write_csv(DATA, out)
    rows = list(csv.DictReader(out.open()))
    assert "(inferred)" not in rows[0]["holds"]
