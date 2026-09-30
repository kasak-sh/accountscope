"""Validate tests/labelled/messages.jsonl: schema, allowed types/facts, and that no
real-looking address domain has crept in.

Usage: .venv/bin/python scripts/lint_labelled.py [path/to/messages.jsonl]

Exits 0 and prints "ok: <path>" when the file is clean, exits 1 and prints one message
per problem otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "tests" / "labelled" / "messages.jsonl"

TYPES = {"otp", "verify", "reset", "signup", "receipt", "statement", "notice", "marketing", "other"}
FACT_TYPES = {"card", "phone", "address"}
REQUIRED_KEYS = {"subject", "list_unsubscribe", "body", "type", "facts"}

# A domain-shaped token immediately after "@" (no space, unlike a calendar subject's
# "@ Thu 3pm"): one or more dot-separated labels ending the match at the last label.
_AT_DOMAIN = re.compile(r"@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)+)")
_ALLOWED_DOMAIN = re.compile(
    r"^(?:[A-Za-z0-9-]+\.)*example\.(?:com|org|net)$"  # example.com / org / net, any subdomain
    r"|^(?:[A-Za-z0-9-]+\.)+example$",                 # the .example TLD, e.g. store.example
    re.IGNORECASE,
)


def check(path: Path | str) -> list[str]:
    """Return a list of human-readable problem descriptions; empty means the file is clean."""
    path = Path(path)
    errors: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON ({exc})")
            continue
        if not isinstance(row, dict) or set(row.keys()) != REQUIRED_KEYS:
            got = sorted(row.keys()) if isinstance(row, dict) else type(row).__name__
            errors.append(f"line {lineno}: expected exactly the keys {sorted(REQUIRED_KEYS)}, got {got}")
            continue
        if row["type"] not in TYPES:
            errors.append(f"line {lineno}: type {row['type']!r} is not one of {sorted(TYPES)}")
        facts = row.get("facts")
        if not isinstance(facts, list):
            errors.append(f"line {lineno}: 'facts' must be a list")
        else:
            for i, fact in enumerate(facts):
                if not isinstance(fact, dict) or "fact" not in fact or "value" not in fact:
                    errors.append(f"line {lineno}: facts[{i}] must be an object with 'fact' and 'value' keys")
                    continue
                if fact["fact"] not in FACT_TYPES:
                    errors.append(f"line {lineno}: facts[{i}]['fact'] {fact['fact']!r} is not one of {sorted(FACT_TYPES)}")
        for field in ("subject", "body"):
            text = row.get(field)
            if not isinstance(text, str):
                continue
            for m in _AT_DOMAIN.finditer(text):
                domain = m.group(1)
                if not _ALLOWED_DOMAIN.match(domain):
                    errors.append(f"line {lineno}: {field} contains a non-example address domain: '@{domain}'")
    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    errors = check(path)
    if errors:
        for message in errors:
            print(message)
        print(f"{len(errors)} problem(s) found in {path}")
        return 1
    print(f"ok: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
