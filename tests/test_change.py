import json

import pytest

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
    data["organisations"].append({
        "key": "shop.example", "name": "Online Shop", "sender_addresses": ["orders@shop.example"],
        "types": {"receipt": 10}, "marketing_only": False, "first_seen": "2019-01-01", "last_seen": "2024-06-01",
        "writes_to": [{"address": "me@gmail.com", "last": "2024-06-01", "count": 10}],
        "holds": [{"fact": "address", "value": "London SW1A 1AA", "evidence": "e", "seen": "2024-06-01", "confidence": "medium", "inferred": True}],
        "delete": None, "category": "shopping", "via_relay": False})
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
    # example.com writes only to me@gmail.com, so use the card kind to see its holds surfaced.
    term = render_terminal(build_checklist(make_data(), "card", None), "card", None, None)
    assert "holds card ending 4421" in term


def test_short_card_or_phone_value_is_rejected():
    with pytest.raises(ValueError):
        build_checklist(make_data(), "card", "4")
    with pytest.raises(ValueError):
        build_checklist(make_data(), "phone", "12")


def test_address_change_with_value_matches_substring():
    rows = build_checklist(make_data(), "address", "sw1a")
    assert [r.key for r in rows] == ["shop.example"]


def test_undated_rows_sort_last_within_tier():
    data = make_data()
    data["organisations"].append({
        "key": "tier3a.example", "name": "Tier3 A", "sender_addresses": ["a@tier3a.example"],
        "types": {"other": 1}, "marketing_only": False, "first_seen": "2020-01-01", "last_seen": "2024-01-01",
        "writes_to": [{"address": "old@isp.net", "last": "2024-01-01", "count": 1}],
        "holds": [], "delete": None, "category": "other", "via_relay": False})
    data["organisations"].append({
        "key": "tier3b.example", "name": "Tier3 B", "sender_addresses": ["b@tier3b.example"],
        "types": {"other": 1}, "marketing_only": False, "first_seen": "2020-01-01", "last_seen": "2024-01-01",
        "writes_to": [{"address": "old@isp.net", "last": None, "count": 1}],
        "holds": [], "delete": None, "category": "other", "via_relay": False})
    rows = build_checklist(data, "email", "old@isp.net")
    keys = [r.key for r in rows]
    assert keys.index("tier3a.example") < keys.index("tier3b.example")


def test_terminal_truncates_newsletters_after_eight():
    data = {"organisations": [
        {"key": f"news{i}.example", "name": f"Newsletter {i}", "sender_addresses": [f"n{i}@news{i}.example"],
         "types": {"marketing": 1}, "marketing_only": True, "first_seen": "2020-01-01", "last_seen": "2024-01-01",
         "writes_to": [{"address": "old@isp.net", "last": "2024-01-01", "count": 1}],
         "holds": [], "delete": None, "category": "other", "via_relay": False}
        for i in range(10)
    ]}
    rows = build_checklist(data, "email", "old@isp.net")
    term = render_terminal(rows, "email", "old@isp.net", None)
    assert "newsletters (10):" in term
    assert term.endswith("...")


def slug_row_data():
    return {"organisations": [{
        "key": "weekly-digest", "name": "Weekly Digest", "sender_addresses": ["b@mcsv.net"],
        "types": {"receipt": 2}, "marketing_only": False, "first_seen": "2024-01-01", "last_seen": "2024-06-01",
        "writes_to": [{"address": "old@isp.net", "last": "2024-06-01", "count": 2}],
        "holds": [], "delete": None, "category": "other", "via_relay": True}]}


def test_link_is_empty_for_a_key_that_is_not_a_domain():
    rows = build_checklist(slug_row_data(), "email", "old@isp.net")
    assert rows[0].link == ""


def test_renderers_say_no_link_when_there_is_none():
    rows = build_checklist(slug_row_data(), "email", "old@isp.net")
    md = render_markdown(rows, "email", "old@isp.net", None)
    assert "no link; search your mail for Weekly Digest" in md
    assert "https://weekly-digest" not in md
    term = render_terminal(rows, "email", "old@isp.net", None)
    assert "no link; search your mail for Weekly Digest" in term
    assert "https://weekly-digest" not in term


def test_newsletter_rows_say_no_link_too():
    data = slug_row_data()
    data["organisations"][0]["marketing_only"] = True
    data["organisations"][0]["types"] = {"marketing": 2}
    rows = build_checklist(data, "email", "old@isp.net")
    md = render_markdown(rows, "email", "old@isp.net", None)
    assert "no link; search your mail for Weekly Digest" in md
    assert "](" not in md.split("## newsletters")[1]
