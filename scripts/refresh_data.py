"""Refresh bundled datasets. Run at release time only; the installed package never uses the network.

Usage: python3 scripts/refresh_data.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DATA = Path(__file__).resolve().parent.parent / "accountscope" / "data"
PSL_URL = "https://publicsuffix.org/list/public_suffix_list.dat"
JDM_URL = "https://raw.githubusercontent.com/jdm-contrib/jdm/master/_data/sites.json"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def refresh_psl() -> int:
    text = fetch(PSL_URL).decode("utf-8")
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("//")]
    (DATA / "public_suffix_list.dat").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def refresh_jdm() -> int:
    sys.path.insert(0, str(DATA.parent.parent))
    from accountscope.orgs import registrable_domain  # uses the PSL written just above

    sites = json.loads(fetch(JDM_URL).decode("utf-8"))
    out: dict[str, dict] = {}
    for site in sites:
        url = site.get("url") or ""
        domains = list(site.get("domains") or [])
        host = urlparse(url).hostname or ""
        if host:
            domains.append(host)
        for d in domains:
            key = registrable_domain(d)
            if key and key not in out:
                out[key] = {"name": site.get("name", key), "url": url, "difficulty": site.get("difficulty", "unknown")}
    (DATA / "justdeleteme.json").write_text(json.dumps(out, indent=0, sort_keys=True), encoding="utf-8")
    return len(out)


if __name__ == "__main__":
    print("public suffix rules:", refresh_psl())
    print("justdeleteme domains:", refresh_jdm())
