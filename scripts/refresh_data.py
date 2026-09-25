"""Refresh bundled datasets. Run at release time only; the installed package never uses the network.

Usage: python3 scripts/refresh_data.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DATA = Path(__file__).resolve().parent.parent / "accountscope" / "data"
PSL_URL = "https://publicsuffix.org/list/public_suffix_list.dat"
JDM_URL = "https://raw.githubusercontent.com/jdm-contrib/jdm/master/_data/sites.json"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def refresh_psl() -> int:
    text = fetch(PSL_URL).decode("utf-8")
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("//")]
    (DATA / "public_suffix_list.dat").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def index_sites(sites: list[dict]) -> dict[str, dict]:
    """Registrable domain -> deletion entry.

    A site's own `domains` list is authoritative. The host of the deletion URL is used
    only when a site lists no domains at all: justdelete.me documents many services on
    a parent's help site (Blogger on support.google.com, Bountysource on github.com),
    and indexing that host handed google.com to Blogger and github.com to Bountysource.
    On a collision the entry that names the key in its own `domains` wins.
    """
    sys.path.insert(0, str(DATA.parent.parent))
    from accountscope.orgs import registrable_domain  # uses the PSL written just above

    out: dict[str, dict] = {}
    claimed: set[str] = set()
    for site in sites:
        url = site.get("url") or ""
        listed = [d for d in (site.get("domains") or []) if d]
        if listed:
            domains, exact = listed, True
        else:
            host = urlparse(url).hostname or ""
            domains, exact = ([host] if host else []), False
        for domain in domains:
            key = registrable_domain(domain)
            if not key:
                continue
            if key in out and not (exact and key not in claimed):
                continue
            out[key] = {"name": site.get("name") or key, "url": url,
                        "difficulty": site.get("difficulty", "unknown")}
            if exact:
                claimed.add(key)
    return out


def refresh_jdm() -> int:
    sites = json.loads(fetch(JDM_URL).decode("utf-8"))
    out = index_sites(sites)
    (DATA / "justdeleteme.json").write_text(json.dumps(out, indent=0, sort_keys=True), encoding="utf-8")
    return len(out)


def write_versions() -> dict:
    versions = {"public_suffix_list": _today(), "justdeleteme": _today()}
    (DATA / "versions.json").write_text(json.dumps(versions, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return versions


if __name__ == "__main__":
    print("public suffix rules:", refresh_psl())
    print("justdeleteme domains:", refresh_jdm())
    print("versions:", write_versions())
