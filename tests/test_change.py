import json

from accountscope.change import TIER1, Row, build_checklist, render_markdown, render_terminal
from tests.test_report import DATA


def make_data():
    data = json.loads(json.dumps(DATA))
    data["organisations"].append({
        "key": "power.example", "name": "City Power", "sender_addresses": ["bills@power.example"],
        "types": {"statement": 20}, "marketing_only": False, "first_seen": "2018-01-01", "last_seen": "2025-12-01",
        "writes_to": [{"address": "old@isp.net", "last": "2025-12-01", "count": 20}],
        "holds": [{"fact": "phone", "value": "ending 1234", "evidence": "e", "seen": "2025-11-01", "confidence": "medium", "inferred": True}],
        "delete": None, "category": "utilities", "via_relay": False})
    data["organisations"].append({
        "key": "gov.example", "name": "Tax Office", "sender_addresses": ["no-reply@gov.example"],
        "types": {"notice": 5}, "marketing_only": False, "first_seen": "2021-01-01", "last_seen": "2022-01-01",
        "writes_to": [{"address": "old@isp.net", "last": "2022-01-01", "count": 5}],
        "holds": [], "delete": None, "category": "government", "via_relay": False})
    data["organisations"][1]["writes_to"] = [{"address": "old@isp.net", "last": "2026-01-01", "count": 30}]  # newsletter
    return data


def test_email_change_selects_by_writes_to_and_orders_by_tier_then_recency():
    rows = build_checklist(make_data(), "email", "Old+news@ISP.net", "new@example.org")
    assert [r.key for r in rows] == ["gov.example", "power.example", "news.example"]
    assert rows[0].tier == 1 and rows[1].tier == 2 and rows[2].marketing_only is True
    assert rows[1].last == "2025-12-01" and rows[1].link == "https://power.example"
    assert "example.com" not in [r.key for r in rows]      # bank writes only to me@gmail.com


def test_phone_change_with_value_matches_fact_tail():
    rows = build_checklist(make_data(), "phone", "+91 98765 41234")
    assert [r.key for r in rows] == ["power.example"]
    assert rows[0].reason == "holds phone ending 1234"


def test_kind_without_value_adds_check_rows_for_sensitive_categories():
    rows = build_checklist(make_data(), "card", None)
    keys = [r.key for r in rows]
    assert keys[:2] == ["example.com", "gov.example"]      # both tier 1; bank's card fact (2026-09-01) is more recent than the tax office's last mail (2022-01-01)
    assert "example.com" in keys                         # holds card
    assert "power.example" in keys                       # utilities: check
    assert next(r for r in rows if r.key == "gov.example").reason == "check: government organisations commonly hold a card"
    assert "news.example" not in keys


def test_renderers():
    rows = build_checklist(make_data(), "email", "old@isp.net", "new@example.org")
    md = render_markdown(rows, "email", "old@isp.net", "new@example.org")
    assert md.startswith("# Change email: old@isp.net -> new@example.org")
    assert "- [ ] **Tax Office**" in md and "https://gov.example" in md
    assert "newsletters (1)" in md
    term = render_terminal(rows, "email", "old@isp.net", "new@example.org")
    assert "Tax Office" in term and "2022-01-01" in term
    assert TIER1 == frozenset({"finance", "government"})
