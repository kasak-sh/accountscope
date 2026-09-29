"""Type a message from its subject and headers only. Pure functions over strings."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

TRANSACTIONAL = frozenset({"otp", "verify", "reset", "signup", "receipt", "statement", "notice"})
_DIGITS = re.compile(r"(?<!\d)\d{4,8}(?!\d)")
DIGIT_WINDOW = 30

# Compiled trigger patterns for the one rules object that is worth caching: the single
# memoized load_rules() dict, which lives for the whole process and is never mutated.
# The bundled path therefore compiles exactly once. Every other rules dict — the ad-hoc
# ones callers and tests build — is compiled on the fly instead, because caching those
# would be both unbounded (one entry per caller, never evicted) and stale-prone (a
# caller that edits its own dict between calls would keep getting the old patterns).
_BUNDLED = "bundled"
_pattern_cache: dict[str, dict[str, list[re.Pattern]]] = {}


@lru_cache(maxsize=1)
def load_rules() -> dict:
    text = resources.files("accountscope.data").joinpath("rules.json").read_text(encoding="utf-8")
    return json.loads(text)


def _trigger_pattern(word: str, stem_words: frozenset[str]) -> re.Pattern:
    """A trigger is anchored on its left boundary always, and on its right boundary
    unless it is listed in `stem_words`.

    `(?<!\\w)`/`(?!\\w)` rather than `\\b` so a multi-word phrase ("confirm your",
    "code de vérification") only needs its own start and end to sit on a boundary, and
    so this stays correct for non-ASCII scripts (Hindi) where `\\w` is Unicode-aware.

    German, and to a lesser extent Spanish, Portuguese and French, glue a trigger to
    the noun that follows it: "Verifizierungscode", "Versandbestätigung",
    "Rechnungsnummer", "Passwortänderung", "Kontoauszugsbenachrichtigung",
    "Willkommensangebot". A trailing `(?!\\w)` loses every one of those, so the stems
    those compounds are built on drop it and match as prefixes. Everything else keeps
    both boundaries, which is what stops "reset" firing inside "Unresettable" and
    "confirme" inside "confirmed".
    """
    pattern = r"(?<!\w)" + re.escape(word)
    if word not in stem_words:
        pattern += r"(?!\w)"
    return re.compile(pattern)


def _compiled(rules: dict) -> dict[str, list[re.Pattern]]:
    """Trigger regexes for every rule type (its own "any" list plus its translations).

    Only the memoized load_rules() object is cached, identified with `is`; see the
    _pattern_cache comment above for why nothing else is.
    """
    is_bundled = rules is load_rules()
    if is_bundled:
        cached = _pattern_cache.get(_BUNDLED)
        if cached is not None:
            return cached
    stem_words = frozenset(rules.get("stem_words", []))
    translations = rules.get("translations", {})
    patterns = {
        rule["type"]: [_trigger_pattern(word, stem_words)
                       for word in list(rule["any"]) + list(translations.get(rule["type"], []))]
        for rule in rules.get("types", [])
    }
    if is_bundled:
        _pattern_cache[_BUNDLED] = patterns
    return patterns


def _code_near_trigger(text: str, patterns: list[re.Pattern]) -> bool:
    """A 4-8 digit token that belongs to one of the trigger patterns, rather than any
    digits anywhere in the subject: "Order 12345678 shipped, use code later" is not a
    one-time code, and neither is "use code SAVE20 before 2026 ends".

    A token counts when it starts within DIGIT_WINDOW characters after a trigger match
    ("your code is 483920"), or when the subject opens with it and a trigger follows
    ("483920 is your OTP" — the commonest one-time-code subject there is).
    """
    starts = [m.start() for m in _DIGITS.finditer(text)]
    if not starts:
        return False
    if starts[0] == 0:
        return True
    for pattern in patterns:
        for m in pattern.finditer(text):
            end = m.end()
            if any(end <= start <= end + DIGIT_WINDOW for start in starts):
                return True
    return False


def classify(subject: str, has_list_unsubscribe: bool, rules: dict | None = None) -> str:
    rules = rules if rules is not None else load_rules()
    text = subject.lower()
    patterns = _compiled(rules)
    for rule in rules["types"]:
        rule_patterns = patterns.get(rule["type"], [])
        if any(p.search(text) for p in rule_patterns):
            if has_list_unsubscribe and rule.get("never_with_unsubscribe"):
                continue
            if rule.get("needs_digits") and not _code_near_trigger(text, rule_patterns):
                continue
            return rule["type"]
    return "marketing" if has_list_unsubscribe else "other"
