"""Turn an inventory into a prioritised checklist for an email, phone, address or card change."""
from __future__ import annotations

import re
from dataclasses import dataclass

from accountscope.identity import canonical

KINDS = ("email", "phone", "address", "card")
TIER1 = frozenset({"finance", "government"})
TIER2 = frozenset({"utilities", "health", "telecom", "travel"})
CHECK_CATEGORIES = frozenset({"finance", "government", "utilities", "health"})


@dataclass
class Row:
    name: str
    key: str
    category: str
    tier: int
    last: str | None
    holds: list[str]
    link: str
    reason: str
    marketing_only: bool


def _tier(category: str) -> int:
    if category in TIER1:
        return 1
    if category in TIER2:
        return 2
    return 3


def _link(org: dict) -> str:
    delete = org.get("delete") or {}
    return delete.get("url") or f"https://{org['key']}"


def _row(org: dict, last: str | None, reason: str) -> Row:
    return Row(name=org["name"], key=org["key"], category=org["category"], tier=_tier(org["category"]), last=last,
               holds=[f"{h['fact']} {h['value']}" for h in org["holds"]], link=_link(org), reason=reason,
               marketing_only=bool(org["marketing_only"]))


def _tail(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[-4:]


def build_checklist(data: dict, kind: str, old: str | None, new: str | None = None) -> list[Row]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    rows: list[Row] = []
    if kind == "email":
        target = canonical(old or "")
        for org in data["organisations"]:
            hit = next((w for w in org["writes_to"] if w["address"] == target), None)
            if hit:
                rows.append(_row(org, hit["last"], f"writes to {target}"))
    else:
        tail = _tail(old)
        for org in data["organisations"]:
            facts = [h for h in org["holds"] if h["fact"] == kind]
            if old:
                if kind == "address":
                    facts = [h for h in facts if old.lower() in h["value"].lower()]
                else:
                    facts = [h for h in facts if tail and h["value"].endswith(tail)]
            if facts:
                latest = max(facts, key=lambda h: h["seen"])
                rows.append(_row(org, latest["seen"], f"holds {kind} {latest['value']}"))
            elif not old and org["category"] in CHECK_CATEGORIES and not org["marketing_only"]:
                rows.append(_row(org, org["last_seen"], f"check: {org['category']} organisations commonly hold a {kind}"))
    rows.sort(key=lambda r: (r.marketing_only, r.tier, -(int((r.last or "0000-00-00").replace("-", "")))))
    return rows


def _split(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    return [r for r in rows if not r.marketing_only], [r for r in rows if r.marketing_only]


def render_markdown(rows: list[Row], kind: str, old: str | None, new: str | None) -> str:
    title = f"# Change {kind}: {old or 'any'}" + (f" -> {new}" if new else "")
    main, newsletters = _split(rows)
    lines = [title, ""]
    tier = None
    for r in main:
        if r.tier != tier:
            tier = r.tier
            lines.append({1: "## First: money and government", 2: "## Then: utilities, health, telecom, travel", 3: "## Everything else"}[tier])
        holds = f" · holds {', '.join(r.holds)}" if r.holds else ""
        lines.append(f"- [ ] **{r.name}** ({r.key}) · last {r.last or 'undated'} · {r.reason}{holds} · [change it here]({r.link})")
    if newsletters:
        lines.append("")
        lines.append(f"## newsletters ({len(newsletters)})")
        for r in newsletters:
            lines.append(f"- [ ] {r.name} ({r.key}) · [unsubscribe or update]({r.link})")
    return "\n".join(lines) + "\n"


def render_terminal(rows: list[Row], kind: str, old: str | None, new: str | None) -> str:
    main, newsletters = _split(rows)
    lines = [f"change {kind}: {old or 'any'}" + (f" -> {new}" if new else ""), ""]
    lines.append(f"  {'tier':<4} {'last':<11} {'organisation':<34} reason")
    for r in main:
        lines.append(f"  {r.tier:<4} {r.last or '-':<11} {r.name[:33]:<34} {r.reason}")
        lines.append(f"       {'':<11} {'':<34} {r.link}")
    if newsletters:
        lines.append(f"  newsletters ({len(newsletters)}): " + ", ".join(r.name for r in newsletters[:8]) + (" ..." if len(newsletters) > 8 else ""))
    return "\n".join(lines)
