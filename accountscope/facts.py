"""Pass-2 extractors: what an organisation holds about the user, from transactional message text."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from accountscope.inventory import Fact

EVIDENCE_WIDTH = 120
MIN_TAIL_DIGITS = 4
LONG_DIGIT_RUN = re.compile(r"\d{7,}")

CARD = re.compile(
    r"\b(?:card|visa|mastercard|amex|debit|credit)\b[^.\n]{0,40}?"
    r"(?:ending(?: in)?|last (?:4|four) digits)[^0-9\n]{0,10}(\d{4})",
    re.IGNORECASE,
)
PHONE = re.compile(
    r"\b(?:code|text|sms|message)\b[^.\n]{0,60}?(?:phone|mobile|number)[^0-9*x•\n]{0,20}([0-9*x•]{6,})",
    re.IGNORECASE,
)
ADDRESS_CUE = re.compile(r"(?:ship(?:ping)?|deliver(?:y)?|billing)\s+address\s*:?", re.IGNORECASE)
POSTCODE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}"      # UK
    r"|\d{5}(?:-\d{4})?"                          # US ZIP
    r"|\d{6}"                                     # Indian PIN
    r"|\d{4})\b"                                  # 4-digit (AU, NZ, AT, CH, BE, DK...)
)
STRONG_POSTCODE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}"      # UK
    r"|\d{5}(?:-\d{4})?"                          # US ZIP
    r"|\d{6})\b"                                  # Indian PIN
)


@dataclass(frozen=True)
class FactHit:
    fact: str
    value: str
    evidence: str
    seen: str


def _mask_digits(text: str) -> str:
    """Keep the last four digits of any run of seven or more. An evidence snippet is
    there to let you recognise a fact, never to carry a full number out of a body."""
    return LONG_DIGIT_RUN.sub(lambda m: "*" * (len(m.group(0)) - 4) + m.group(0)[-4:], text)


def _snippet(text: str, start: int, end: int) -> str:
    dot = text.rfind(". ", 0, start)
    nl = text.rfind("\n", 0, start)
    sent_start = max(dot + 2 if dot >= 0 else 0, nl + 1 if nl >= 0 else 0)
    window = text[sent_start:sent_start + EVIDENCE_WIDTH]
    window = re.sub(r"\s+", " ", window.replace("\n", " ")).strip()
    return _mask_digits(window[:EVIDENCE_WIDTH])


def extract_facts(text: str, seen: str) -> list[FactHit]:
    hits: list[FactHit] = []
    for m in CARD.finditer(text):
        hits.append(FactHit("card", f"ending {m.group(1)}", _snippet(text, m.start(), m.end()), seen))
    for m in PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) < MIN_TAIL_DIGITS:
            continue
        hits.append(FactHit("phone", f"ending {digits[-4:]}", _snippet(text, m.start(), m.end()), seen))
    for m in ADDRESS_CUE.finditer(text):
        window = text[m.end(): m.end() + 300]
        lines = [line.strip() for line in window.splitlines() if line.strip()][:4]
        candidates = [line for line in lines if len(line) < 80 and re.search(r"[A-Za-z]", line)]
        strong_line = None
        weak_line = None
        for line in candidates:
            if STRONG_POSTCODE.search(line):
                strong_line = line
            if POSTCODE.search(line):
                weak_line = line
        match_line = strong_line if strong_line is not None else weak_line
        if match_line:
            hits.append(FactHit("address", match_line, _snippet(text, m.start(), m.start() + len(match_line)), seen))
    return hits


def merge_facts(hits: Iterable[FactHit]) -> list[Fact]:
    grouped: dict[tuple[str, str], list[FactHit]] = defaultdict(list)
    for hit in hits:
        grouped[(hit.fact, hit.value)].append(hit)
    facts: list[Fact] = []
    for (fact, value), group in grouped.items():
        latest = max(group, key=lambda h: h.seen)
        distinct_dates = {h.seen for h in group}
        confidence = "high" if len(distinct_dates) >= 2 else "medium"
        facts.append(Fact(fact, value, latest.evidence, latest.seen, confidence))
    facts.sort(key=lambda f: (f.fact, f.value))
    return facts
