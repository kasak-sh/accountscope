"""Map a sender to an organisation using the public-suffix list and a relay list."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources


def _data_text(name: str) -> str:
    return resources.files("accountscope.data").joinpath(name).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _psl() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    rules, wild, exceptions = set(), set(), set()
    for line in _data_text("public_suffix_list.dat").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("!"):
            exceptions.add(line[1:])
        elif line.startswith("*."):
            wild.add(line[2:])
        else:
            rules.add(line)
    return frozenset(rules), frozenset(wild), frozenset(exceptions)


def _public_suffix_length(labels: list[str]) -> int:
    rules, wild, exceptions = _psl()
    best = 0
    for i in range(len(labels)):
        candidate = ".".join(labels[i:])
        n = len(labels) - i
        if candidate in exceptions:
            return n - 1
        if candidate in rules and n > best:
            best = n
        parent = ".".join(labels[i + 1:])
        if parent and parent in wild and n > best:
            best = n
    return best or 1


def registrable_domain(host: str) -> str:
    host = host.strip().lower().rstrip(".")
    if not host or "." not in host:
        return host
    labels = host.split(".")
    suffix = _public_suffix_length(labels)
    if suffix >= len(labels):
        return host
    return ".".join(labels[-(suffix + 1):])


@lru_cache(maxsize=1)
def load_relays() -> frozenset[str]:
    return frozenset(json.loads(_data_text("rules.json"))["relays"])


@dataclass(frozen=True)
class OrgIdentity:
    key: str
    name: str
    via_relay: bool


def _slug(name: str) -> str:
    """A display name reduced to an ASCII key, or "" when nothing survives."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _domain_of(address: str) -> str:
    return registrable_domain(address.rsplit("@", 1)[1]) if "@" in address else ""


def identify(sender: str, sender_name: str, reply_to: str, relays: frozenset[str]) -> OrgIdentity:
    domain = _domain_of(sender)
    if domain and domain in relays:
        reply_domain = _domain_of(reply_to)
        if reply_domain and reply_domain not in relays:
            return OrgIdentity(reply_domain, sender_name or reply_domain, True)
        slug = _slug(sender_name)
        if slug:
            return OrgIdentity(slug, sender_name, True)
        # A name that slugs to nothing (Devanagari, punctuation only, or no name at
        # all) must not collapse every such relay sender under one key — but it must
        # also never surface the raw envelope address as the key or name.
        key = f"relay:{domain}"
        return OrgIdentity(key, key, True)
    key = domain or "unknown"
    return OrgIdentity(key, sender_name or key, False)
