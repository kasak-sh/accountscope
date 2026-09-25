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
         "holds": [{"fact": "card", "value": "ending 4421", "evidence": "e", "seen": "2026-09-01", "confidence": "high", "inferred": True}],
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
