from datetime import datetime, timezone

from accountscope.identity import SelfAddress
from accountscope.inventory import PASS2_CAP, Aggregator, Fact, Organisation, categorise
from accountscope.mbox import Message
from accountscope.orgs import OrgIdentity


def msg(key, sender, name, subject, date, recipients, unsub=False):
    return Message(key=str(key), sender=sender, sender_name=name, reply_to="", subject=subject,
                   date=datetime(*date, tzinfo=timezone.utc), recipients=frozenset(recipients),
                   has_list_unsubscribe=unsub)


def test_aggregator_builds_writes_to_only_for_self_addresses():
    agg = Aggregator()
    bank = OrgIdentity("example.com", "Example Bank", False)
    agg.add(msg(1, "alerts@example.com", "Example Bank", "Statement", (2019, 1, 4), {"old@isp.net"}), bank, "statement")
    agg.add(msg(2, "alerts@example.com", "Example Bank", "Statement", (2024, 9, 3), {"me+bank@gmail.com", "friend@x.org"}), bank, "statement")
    agg.add(msg(3, "news@example.com", "Example Bank", "Sale", (2024, 9, 5), {"me@gmail.com"}, unsub=True), bank, "marketing")
    inv = agg.finish({"path": "x"}, [SelfAddress("me@gmail.com", ["me+bank@gmail.com"], 2, False), SelfAddress("old@isp.net", [], 1, True)])
    org = inv.organisations[0]
    assert org.key == "example.com" and org.name == "Example Bank"
    assert set(org.sender_addresses) == {"alerts@example.com", "news@example.com"}
    assert org.types == {"statement": 2, "marketing": 1}
    assert org.first_seen == "2019-01-04" and org.last_seen == "2024-09-05"
    assert org.writes_to == {
        "me@gmail.com": {"last": "2024-09-05", "count": 2},
        "old@isp.net": {"last": "2019-01-04", "count": 1},
    }
    assert "friend@x.org" not in org.writes_to
    assert org.marketing_only is False
    assert [k for _, k in org.pass2] == ["2", "1"]          # transactional only, most recent first


def test_pass2_is_capped_to_most_recent():
    agg = Aggregator()
    ident = OrgIdentity("shop.example", "Shop", False)
    for i in range(60):
        agg.add(msg(i, "a@shop.example", "Shop", "Receipt", (2020, 1, 1 + i % 28), {"me@gmail.com"}), ident, "receipt")
    inv = agg.finish({}, [SelfAddress("me@gmail.com", [], 60, False)])
    org = inv.organisations[0]
    assert len(org.pass2) == PASS2_CAP
    assert org.pass2[0][0] >= org.pass2[-1][0]


def test_marketing_only_and_name_by_frequency():
    agg = Aggregator()
    agg.add(msg(1, "n@news.example", "Newsletter", "Sale", (2024, 1, 1), {"me@gmail.com"}, True), OrgIdentity("news.example", "Newsletter", False), "marketing")
    agg.add(msg(2, "n@news.example", "The Newsletter", "Sale", (2024, 1, 2), {"me@gmail.com"}, True), OrgIdentity("news.example", "The Newsletter", False), "marketing")
    agg.add(msg(3, "n@news.example", "The Newsletter", "Sale", (2024, 1, 3), {"me@gmail.com"}, True), OrgIdentity("news.example", "The Newsletter", False), "marketing")
    inv = agg.finish({}, [SelfAddress("me@gmail.com", [], 3, False)])
    org = inv.organisations[0]
    assert org.marketing_only is True and org.name == "The Newsletter" and org.pass2 == []


def test_categorise_prefers_government_then_finance():
    cats = {"government": ["gov"], "finance": ["bank"], "shopping": ["shop"]}
    assert categorise(Organisation(key="tax.gov.in"), cats) == "government"
    assert categorise(Organisation(key="mybank.com"), cats) == "finance"
    org = Organisation(key="acme.example")
    org.types["statement"] = 3
    assert categorise(org, cats) == "finance"
    assert categorise(Organisation(key="acme.example"), cats) == "other"


def test_to_dict_shape_and_no_third_party_data():
    agg = Aggregator()
    agg.add(msg(1, "alerts@example.com", "Example Bank", "Statement", (2024, 9, 3), {"me@gmail.com", "friend@x.org"}), OrgIdentity("example.com", "Example Bank", False), "statement")
    inv = agg.finish({"path": "t.mbox", "messages": 1, "skipped": 0, "date_range": ["2024-09-03", "2024-09-03"]},
                     [SelfAddress("me@gmail.com", [], 1, False)])
    inv.organisations[0].holds = [Fact("card", "ending 4421", "your card ending 4421", "2024-09-03", "medium")]
    data = inv.to_dict()
    assert data["schema"] == "accountscope/1"
    assert data["self"] == [{"address": "me@gmail.com", "aliases": [], "messages": 1, "declared": False}]
    org = data["organisations"][0]
    assert set(org) == {"key", "name", "sender_addresses", "types", "marketing_only", "first_seen", "last_seen",
                        "writes_to", "holds", "delete", "category", "via_relay"}
    assert org["writes_to"] == [{"address": "me@gmail.com", "last": "2024-09-03", "count": 1}]
    assert org["holds"][0] == {"fact": "card", "value": "ending 4421", "evidence": "your card ending 4421",
                               "seen": "2024-09-03", "confidence": "medium", "inferred": True}
    assert "friend@x.org" not in str(data)
    assert "Statement" not in str(data)


def test_personal_mail_senders_are_dropped_and_counted():
    agg = Aggregator()
    agg.add(msg(1, "alerts@example.com", "Example Bank", "Statement", (2024, 9, 3), {"me@gmail.com"}),
            OrgIdentity("example.com", "Example Bank", False), "statement")
    agg.add(msg(2, "jordan@gmail.com", "Jordan", "Lunch?", (2024, 9, 4), {"me@gmail.com"}),
            OrgIdentity("gmail.com", "Jordan", False), "other")
    agg.add(msg(3, "sam@proton.me", "Sam", "Re: keys", (2024, 9, 5), {"me@gmail.com"}),
            OrgIdentity("proton.me", "Sam", False), "other")
    source = {"path": "t.mbox", "messages": 3, "personal_senders_skipped": 0}
    inv = agg.finish(source, [SelfAddress("me@gmail.com", [], 3, False)])
    data = inv.to_dict()
    assert [o["key"] for o in data["organisations"]] == ["example.com"]
    assert data["source"]["personal_senders_skipped"] == 2
    assert "jordan@gmail.com" not in str(data)
    assert "sam@proton.me" not in str(data)


def test_to_dict_emits_only_the_five_most_frequent_sender_addresses():
    agg = Aggregator()
    ident = OrgIdentity("shop.example", "Shop", False)
    # eight distinct senders; "a0@" is seen most often, "a7@" least.
    for i in range(8):
        for _ in range(8 - i):
            agg.add(msg(f"{i}", f"a{i}@shop.example", "Shop", "Receipt", (2024, 1, 1 + i), {"me@gmail.com"}), ident, "receipt")
    inv = agg.finish({}, [SelfAddress("me@gmail.com", [], 36, False)])
    emitted = inv.to_dict()["organisations"][0]["sender_addresses"]
    assert emitted == ["a0@shop.example", "a1@shop.example", "a2@shop.example",
                       "a3@shop.example", "a4@shop.example"]


def test_sender_addresses_with_equal_counts_tie_break_on_address():
    agg = Aggregator()
    ident = OrgIdentity("shop.example", "Shop", False)
    for name in ("z@shop.example", "m@shop.example", "a@shop.example"):
        agg.add(msg(name, name, "Shop", "Receipt", (2024, 1, 1), {"me@gmail.com"}), ident, "receipt")
    inv = agg.finish({}, [SelfAddress("me@gmail.com", [], 3, False)])
    assert inv.to_dict()["organisations"][0]["sender_addresses"] == [
        "a@shop.example", "m@shop.example", "z@shop.example"]


def bundled_categories():
    from accountscope.classify import load_rules
    return load_rules()["categories"]


def named(key, name):
    org = Organisation(key=key)
    org.names[name] += 1
    return org


def test_categorise_matches_whole_tokens_not_substrings():
    cats = bundled_categories()
    assert categorise(Organisation(key="netflix.com"), cats) != "social"        # "x.com" in "netflix.com"
    assert categorise(Organisation(key="gitlab.com"), cats) != "health"         # "lab" in "gitlab"
    assert categorise(Organisation(key="taxi.example"), cats) != "finance"      # "tax" in "taxi"
    assert categorise(named("news.example", "Mastercard Newsletter"), cats) != "finance"


def test_categorise_still_matches_real_organisations():
    cats = bundled_categories()
    assert categorise(Organisation(key="mybank.com"), cats) == "finance"
    assert categorise(Organisation(key="x.com"), cats) == "social"
    assert categorise(Organisation(key="uidai.nic.in"), cats) == "government"
    assert categorise(Organisation(key="att.com"), cats) == "telecom"
    assert categorise(named("billing.example", "Tata Power Ltd"), cats) == "utilities"
    assert categorise(Organisation(key="t-mobile.com"), cats) == "telecom"
