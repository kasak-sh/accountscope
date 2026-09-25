"""Type a message from its subject and headers only. Pure functions over strings."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

TRANSACTIONAL = frozenset({"otp", "verify", "reset", "signup", "receipt", "statement", "notice"})
_DIGITS = re.compile(r"(?<!\d)\d{4,8}(?!\d)")
DIGIT_WINDOW = 30


@lru_cache(maxsize=1)
def load_rules() -> dict:
    text = resources.files("accountscope.data").joinpath("rules.json").read_text(encoding="utf-8")
    return json.loads(text)


def _code_near_trigger(text: str, words: list[str]) -> bool:
    """A 4-8 digit token that belongs to one of the trigger words, rather than any
    digits anywhere in the subject: "Order 12345678 shipped, use code later" is not a
    one-time code, and neither is "use code SAVE20 before 2026 ends".

    A token counts when it starts within DIGIT_WINDOW characters after a trigger word
    ("your code is 483920"), or when the subject opens with it and a trigger follows
    ("483920 is your OTP" — the commonest one-time-code subject there is).
    """
    starts = [m.start() for m in _DIGITS.finditer(text)]
    if not starts:
        return False
    if starts[0] == 0:
        return True
    for word in words:
        at = text.find(word)
        while at >= 0:
            end = at + len(word)
            if any(end <= start <= end + DIGIT_WINDOW for start in starts):
                return True
            at = text.find(word, at + 1)
    return False


def classify(subject: str, has_list_unsubscribe: bool, rules: dict | None = None) -> str:
    rules = rules if rules is not None else load_rules()
    text = subject.lower()
    translations = rules.get("translations", {})
    for rule in rules["types"]:
        words = list(rule["any"]) + list(translations.get(rule["type"], []))
        if any(word in text for word in words):
            if has_list_unsubscribe and rule.get("never_with_unsubscribe"):
                continue
            if rule.get("needs_digits") and not _code_near_trigger(text, words):
                continue
            return rule["type"]
    return "marketing" if has_list_unsubscribe else "other"
