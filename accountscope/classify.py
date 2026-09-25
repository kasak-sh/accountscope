"""Type a message from its subject and headers only. Pure functions over strings."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

TRANSACTIONAL = frozenset({"otp", "verify", "reset", "signup", "receipt", "statement", "notice"})
_DIGITS = re.compile(r"(?<!\d)\d{4,8}(?!\d)")


@lru_cache(maxsize=1)
def load_rules() -> dict:
    text = resources.files("accountscope.data").joinpath("rules.json").read_text(encoding="utf-8")
    return json.loads(text)


def classify(subject: str, has_list_unsubscribe: bool, rules: dict | None = None) -> str:
    rules = rules if rules is not None else load_rules()
    text = subject.lower()
    translations = rules.get("translations", {})
    for rule in rules["types"]:
        words = list(rule["any"]) + list(translations.get(rule["type"], []))
        if any(word in text for word in words):
            if rule.get("needs_digits") and not _DIGITS.search(text):
                continue
            return rule["type"]
    return "marketing" if has_list_unsubscribe else "other"
