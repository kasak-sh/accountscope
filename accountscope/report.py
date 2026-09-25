"""Terminal summary, JSON record and CSV export."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path


def write_json(data: dict, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)


CSV_FIELDS = ["key", "name", "category", "first_seen", "last_seen", "marketing_only",
              "types", "writes_to", "holds", "delete_url", "delete_difficulty", "sender_addresses"]


FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: str) -> str:
    """A spreadsheet reads a leading =, +, -, @, tab or CR as the start of a formula.
    An organisation name comes from a mail header, so it is attacker-controlled text."""
    return "'" + value if value[:1] in FORMULA_LEADERS else value


def write_csv(data: dict, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for org in data["organisations"]:
            delete = org.get("delete") or {}
            writer.writerow({field: _safe(value) for field, value in {
                "key": org["key"],
                "name": org["name"],
                "category": org["category"],
                "first_seen": org["first_seen"] or "",
                "last_seen": org["last_seen"] or "",
                "marketing_only": "true" if org["marketing_only"] else "false",
                "types": "; ".join(f"{t}={n}" for t, n in org["types"].items()),
                "writes_to": "; ".join(f"{w['address']} ({w['last'] or 'undated'})" for w in org["writes_to"]),
                "holds": "; ".join(f"{h['fact']} {h['value']} [{h['confidence']}]" for h in org["holds"]),
                "delete_url": delete.get("url", ""),
                "delete_difficulty": delete.get("difficulty", ""),
                "sender_addresses": "; ".join(org["sender_addresses"]),
            }.items()})


def render_summary(data: dict, stats_extra: dict, outputs: list[Path]) -> str:
    src = data["source"]
    orgs = data["organisations"]
    lines = []
    lines.append(f"messages: {src['messages']:,}   skipped: {src.get('skipped', 0):,} malformed, "
                 f"{stats_extra.get('no_recipients', 0):,} without recipients, {stats_extra.get('body_failures', 0):,} bodies unreadable, "
                 f"{src.get('personal_senders_skipped', 0):,} personal-mail senders")
    if src.get("date_range"):
        lines.append(f"dates:    {src['date_range'][0]} to {src['date_range'][1]}")
    lines.append("")
    lines.append("your addresses (inferred from recipient headers; fix with --me / --not-me):")
    for s in data["self"]:
        alias = f"  aliases: {', '.join(s['aliases'])}" if s["aliases"] else ""
        flag = " (declared)" if s["declared"] else ""
        lines.append(f"  {s['address']:<40} {s['messages']:>8,} messages{flag}{alias}")
    lines.append("")
    by_cat = Counter(o["category"] for o in orgs)
    marketing_only = sum(1 for o in orgs if o["marketing_only"])
    lines.append(f"organisations: {len(orgs):,}   ({marketing_only:,} newsletters only)")
    lines.append("  " + "   ".join(f"{cat}: {n}" for cat, n in by_cat.most_common()))
    lines.append("")
    lines.append("most active accounts (transactional mail)")
    lines.append(f"  {'messages':>8}  {'last seen':<11} {'holds':<22} organisation")
    ranked = sorted(orgs, key=lambda o: -sum(n for t, n in o["types"].items() if t != "marketing" and t != "other"))
    for o in ranked[:10]:
        transactional = sum(n for t, n in o["types"].items() if t not in ("marketing", "other"))
        holds = ", ".join(h["fact"] for h in o["holds"]) or "-"
        lines.append(f"  {transactional:>8,}  {o['last_seen'] or '-':<11} {holds:<22} {o['name']} ({o['key']})")
    lines.append("")
    lines.append("written:")
    for p in outputs:
        lines.append(f"  {p}")
    return "\n".join(lines)
