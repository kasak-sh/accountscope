"""Decide which recipient addresses belong to the user."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

_PLUS = re.compile(r"^([^+@]+)\+[^@]*(@.+)$")


def canonical(address: str) -> str:
    address = address.strip().lower()
    match = _PLUS.match(address)
    return match.group(1) + match.group(2) if match else address


@dataclass
class SelfAddress:
    address: str
    aliases: list[str]
    messages: int
    declared: bool

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "aliases": sorted(self.aliases),
            "messages": self.messages,
            "declared": self.declared,
        }


class SelfDetector:
    """Counts recipient addresses; an address that dominates the mailbox is the user's."""

    SHARE = 0.02
    FLOOR = 200

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()
        self._aliases: defaultdict[str, set[str]] = defaultdict(set)

    def add(self, recipients: Iterable[str]) -> None:
        for raw in recipients:
            canon = canonical(raw)
            self._counts[canon] += 1
            if canon != raw.strip().lower():
                self._aliases[canon].add(raw.strip().lower())

    def resolve(self, total_messages: int, me: Iterable[str] = (), not_me: Iterable[str] = ()) -> list[SelfAddress]:
        declared = {canonical(a) for a in me}
        excluded = {canonical(a) for a in not_me}
        out: list[SelfAddress] = []
        seen: set[str] = set()
        for address, count in self._counts.most_common():
            if address in excluded:
                continue
            by_floor = count >= self.FLOOR
            by_share = total_messages > 0 and count / total_messages >= self.SHARE
            if address in declared or by_floor or by_share:
                out.append(SelfAddress(address, sorted(self._aliases[address]), count, address in declared))
                seen.add(address)
        for address in sorted(declared - seen - excluded):
            out.append(SelfAddress(address, sorted(self._aliases.get(address, set())), self._counts.get(address, 0), True))
        return out
