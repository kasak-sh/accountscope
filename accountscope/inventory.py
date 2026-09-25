"""The in-memory model: one Organisation per sender organisation, aggregated over the mailbox."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources

from accountscope.classify import TRANSACTIONAL, load_rules
from accountscope.identity import SelfAddress, canonical
from accountscope.mbox import Message
from accountscope.orgs import OrgIdentity

SCHEMA = "accountscope/1"
PASS2_CAP = 25
CATEGORY_ORDER = ["government", "finance", "health", "utilities", "telecom", "travel", "work", "social", "shopping"]


@dataclass
class Fact:
    fact: str
    value: str
    evidence: str
    seen: str
    confidence: str
    inferred: bool = True

    def to_dict(self) -> dict:
        return {"fact": self.fact, "value": self.value, "evidence": self.evidence,
                "seen": self.seen, "confidence": self.confidence, "inferred": self.inferred}


@dataclass
class Organisation:
    key: str
    via_relay: bool = False
    names: Counter = field(default_factory=Counter)
    sender_addresses: Counter = field(default_factory=Counter)
    types: Counter = field(default_factory=Counter)
    first_seen: str | None = None
    last_seen: str | None = None
    recipients: dict = field(default_factory=dict)      # canonical address -> {"last": date, "count": n}; pruned at finish
    writes_to: dict = field(default_factory=dict)       # self address -> {"last": date, "count": n}
    holds: list = field(default_factory=list)           # list[Fact]
    pass2: list = field(default_factory=list)           # list[(date_iso, key)]
    delete: dict | None = None
    category: str = "other"

    @property
    def name(self) -> str:
        return self.names.most_common(1)[0][0] if self.names else self.key

    @property
    def marketing_only(self) -> bool:
        return "marketing" in self.types and not (set(self.types) & TRANSACTIONAL)

    @property
    def transactional_count(self) -> int:
        return sum(n for t, n in self.types.items() if t in TRANSACTIONAL)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "sender_addresses": top_senders(self.sender_addresses),
            "types": dict(sorted(self.types.items())),
            "marketing_only": self.marketing_only,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "writes_to": [{"address": a, "last": w["last"], "count": w["count"]}
                          for a, w in sorted(self.writes_to.items(), key=lambda kv: (kv[1]["last"] or ""), reverse=True)],
            "holds": [f.to_dict() for f in self.holds],
            "delete": self.delete,
            "category": self.category,
            "via_relay": self.via_relay,
        }


@dataclass
class Inventory:
    source: dict
    self_addresses: list
    organisations: list

    def to_dict(self) -> dict:
        ordered = sorted(self.organisations, key=lambda o: (-o.transactional_count, -sum(o.types.values()), o.key))
        return {
            "schema": SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": self.source,
            "self": [s.to_dict() for s in self.self_addresses],
            "organisations": [o.to_dict() for o in ordered],
        }

    def transactional_count(self, org: Organisation) -> int:
        return org.transactional_count


SENDER_ADDRESS_CAP = 5


def top_senders(counts: Counter) -> list[str]:
    """The most frequent sender addresses only: enough to recognise the organisation,
    not a transcript of everyone who wrote from that domain."""
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [address for address, _ in ranked[:SENDER_ADDRESS_CAP]]


@lru_cache(maxsize=1)
def load_personal_mail_domains() -> frozenset[str]:
    return frozenset(load_rules().get("personal_mail_domains", []))


@lru_cache(maxsize=1)
def load_justdeleteme() -> dict:
    text = resources.files("accountscope.data").joinpath("justdeleteme.json").read_text(encoding="utf-8")
    return json.loads(text)


def categorise(org: Organisation, categories: dict) -> str:
    haystack = (org.key + " " + org.name).lower()
    for category in CATEGORY_ORDER:
        if any(word in haystack for word in categories.get(category, [])):
            return category
    if org.types.get("statement"):
        return "finance"
    return "other"


class Aggregator:
    def __init__(self) -> None:
        self.orgs: dict[str, Organisation] = {}

    def add(self, message: Message, identity: OrgIdentity, msg_type: str) -> None:
        org = self.orgs.get(identity.key)
        if org is None:
            org = self.orgs[identity.key] = Organisation(key=identity.key, via_relay=identity.via_relay)
        if identity.name:
            org.names[identity.name] += 1
        if message.sender:
            org.sender_addresses[message.sender] += 1
        org.types[msg_type] += 1
        day = message.date.date().isoformat() if message.date else None
        if day:
            org.first_seen = day if org.first_seen is None else min(org.first_seen, day)
            org.last_seen = day if org.last_seen is None else max(org.last_seen, day)
        for raw in message.recipients:
            entry = org.recipients.setdefault(canonical(raw), {"last": None, "count": 0})
            entry["count"] += 1
            if day and (entry["last"] is None or day > entry["last"]):
                entry["last"] = day
        if msg_type in TRANSACTIONAL:
            org.pass2.append((day or "", message.key))
            if len(org.pass2) > PASS2_CAP * 2:
                org.pass2.sort(reverse=True)
                del org.pass2[PASS2_CAP:]

    def finish(self, source: dict, self_addresses: list[SelfAddress]) -> Inventory:
        self_set = {s.address for s in self_addresses}
        categories = load_rules().get("categories", {})
        personal = load_personal_mail_domains()
        jdm = load_justdeleteme()
        skipped = [key for key in self.orgs if key in personal]
        for key in skipped:
            del self.orgs[key]
        source["personal_senders_skipped"] = source.get("personal_senders_skipped", 0) + len(skipped)
        for org in self.orgs.values():
            org.writes_to = {a: w for a, w in org.recipients.items() if a in self_set}
            org.recipients = {}
            org.pass2.sort(reverse=True)
            del org.pass2[PASS2_CAP:]
            org.delete = jdm.get(org.key)
            org.category = categorise(org, categories)
        return Inventory(source, list(self_addresses), list(self.orgs.values()))
