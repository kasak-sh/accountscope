# accountscope v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A zero-network CLI that reads an mbox export, inventories every organisation holding an account for the user, tags each with which of the user's own addresses it writes to and what it holds, and produces a prioritised change checklist.

**Architecture:** Two-pass streaming over the mbox with an in-memory model (approach A). Pass 1 reads headers only and builds self addresses, organisations, message types and recipient maps; pass 2 opens at most 25 transactional bodies per organisation for held-fact extraction. Outputs are a terminal summary, a versioned JSON record, a self-contained HTML viewer, optional CSV, and a Markdown checklist from the `change` command.

**Tech Stack:** Python 3.10+, standard library only at runtime (`mailbox`, `email`, `html.parser`, `argparse`, `json`, `csv`, `re`), setuptools packaging, pytest 8 for tests.

**Spec:** `docs/superpowers/specs/2026-09-25-accountscope-design.md`

Two refinements of the spec, decided here: (1) the CLI uses subcommands `accountscope scan MBOX` and `accountscope change KIND OLD [NEW] INVENTORY` instead of a `--change` flag, same behaviour; (2) the HTML viewer lives in `accountscope/viewer.py` rather than inside `report.py`, to keep files focused. (3) Recipient addresses are accumulated per organisation during pass 1 and filtered to the self set only at `finish()`, because the self set is not known until pass 1 ends; third-party addresses are discarded there and never written.

## Global Constraints

- `requires-python = ">=3.10"`; no runtime dependencies; `pytest>=8` is the only dev dependency.
- No module in `accountscope/` imports `socket`, `urllib`, `http`, `ssl` or `smtplib`. `tests/conftest.py` makes `socket.socket` raise for every test.
- Package layout and packaging follow `~/personal-dev/logsift` (setuptools, `[project.scripts]`, `tests/` with fixtures).
- JSON schema id is `accountscope/1`. The JSON never contains message bodies, subjects or third-party addresses. `holds.value` is stored only in the masked form the email used; `evidence` ≤ 120 characters.
- Self-address inference: canonical address received ≥ 2% of messages or ≥ 200 messages, or passed with `--me`; `--not-me` removes.
- Pass 2 opens at most 25 transactional messages per organisation, most recent first.
- Held-fact confidence: two hits on different dates → `high`, else `medium`.
- Exit codes: 0 success, 1 unexpected error, 2 bad input.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- MIT licence, author `Kinnari Sharma <kasaksharma15@gmail.com>`, repository `https://github.com/kasak-sh/accountscope`.

---

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Packaging, script entry point, package data, pytest config |
| `accountscope/__init__.py` | `__version__` |
| `accountscope/mbox.py` | Stream an mbox into `Message` records; fetch plain-text bodies in pass 2; `NotAnMbox` |
| `accountscope/identity.py` | Canonicalise addresses; infer the user's own addresses |
| `accountscope/orgs.py` | Registrable domain via bundled public-suffix list; sender → `OrgIdentity` with relay unwrapping |
| `accountscope/classify.py` | Subject/header → message type via `data/rules.json` |
| `accountscope/inventory.py` | `Organisation`, `Fact`, `Inventory`, `Aggregator`; categories; JustDeleteMe join; `to_dict` |
| `accountscope/facts.py` | Pass-2 extractors for card, phone, postal address; merge into `Fact`s |
| `accountscope/change.py` | Inventory dict + change request → tiered rows; Markdown and terminal rendering |
| `accountscope/report.py` | Terminal summary, atomic JSON write, CSV |
| `accountscope/viewer.py` | Self-contained HTML viewer with embedded JSON and `<noscript>` table |
| `accountscope/cli.py` | argparse, `scan` and `change` pipelines, exit codes |
| `accountscope/data/rules.json` | Relays, type rules, translations, category keywords |
| `accountscope/data/public_suffix_list.dat` | Bundled PSL (fetched at release by `scripts/refresh_data.py`) |
| `accountscope/data/justdeleteme.json` | Bundled JustDeleteMe map, domain → {name, url, difficulty} |
| `scripts/refresh_data.py` | The only network code; not installed |
| `tests/conftest.py` | Socket guard fixture |
| `tests/helpers.py` | `make_mbox()` fixture builder |
| `tests/test_<module>.py` | One per module |
| `tests/labelled/messages.jsonl` + `tests/test_precision.py` | Labelled set and precision gate |
| `docs/precision.md`, `README.md`, `CHANGELOG.md`, `LICENSE` | Docs |

---

### Task 1: Package scaffold and the network guard

**Files:**
- Create: `pyproject.toml`, `accountscope/__init__.py`, `accountscope/data/.gitkeep`, `LICENSE`, `README.md`, `CHANGELOG.md`, `.gitignore`
- Create: `tests/conftest.py`, `tests/helpers.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Produces: `accountscope.__version__` (str); `tests/helpers.make_mbox(tmp_path, messages: list[str]) -> pathlib.Path` that writes an mbox file from raw RFC 822 message strings.

- [ ] **Step 1: Write the failing tests**

`tests/test_scaffold.py`:
```python
import socket
import pytest

import accountscope
from tests.helpers import make_mbox


def test_version_is_set():
    assert accountscope.__version__ == "0.1.0"


def test_network_is_blocked_in_tests():
    with pytest.raises(Exception, match="forbidden"):
        socket.socket()


def test_make_mbox_writes_from_separators(tmp_path):
    path = make_mbox(tmp_path, ["From: a@example.com\nTo: me@x.org\nSubject: hi\n\nbody\n"])
    text = path.read_text()
    assert text.startswith("From a@example.com ")
    assert "Subject: hi" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/personal-dev/accountscope && python3 -m pytest tests/test_scaffold.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'accountscope'` (or `tests.helpers`).

- [ ] **Step 3: Create the scaffold**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "accountscope"
version = "0.1.0"
description = "Inventory every organisation that holds an account for you from a mailbox export, tagged with which of your addresses each one uses. Zero network."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Kinnari Sharma", email = "kasaksharma15@gmail.com" }]
keywords = ["accounts", "mbox", "privacy", "email", "inventory", "cli"]
classifiers = [
  "Environment :: Console",
  "Programming Language :: Python :: 3",
  "Topic :: Communications :: Email",
]

[project.scripts]
accountscope = "accountscope.cli:main"

[project.urls]
Repository = "https://github.com/kasak-sh/accountscope"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["accountscope*"]

[tool.setuptools.package-data]
accountscope = ["data/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`accountscope/__init__.py`:
```python
"""accountscope: inventory the organisations that hold an account for you, from a mailbox export."""

__version__ = "0.1.0"
```

`accountscope/data/.gitkeep`: empty file.

`tests/__init__.py`: empty file (so `from tests.helpers import ...` resolves).

`tests/conftest.py`:
```python
import socket

import pytest


class NetworkForbidden(Exception):
    pass


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """accountscope promises zero network. Any socket opened during tests is a bug."""

    def _blocked(*args, **kwargs):
        raise NetworkForbidden("network access is forbidden in accountscope tests")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
```

`tests/helpers.py`:
```python
from __future__ import annotations

from email.utils import parseaddr
from pathlib import Path


def make_mbox(tmp_path: Path, messages: list[str], name: str = "test.mbox") -> Path:
    """Write raw RFC 822 messages into an mbox file with 'From ' separators."""
    chunks = []
    for raw in messages:
        raw = raw.replace("\r\n", "\n")
        sender = "unknown@example.com"
        for line in raw.split("\n"):
            if line.lower().startswith("from:"):
                sender = parseaddr(line[5:])[1] or sender
                break
        body_safe = "\n".join((">" + l if l.startswith("From ") else l) for l in raw.split("\n"))
        chunks.append(f"From {sender} Mon Jan  1 00:00:00 2024\n{body_safe.rstrip()}\n\n")
    path = tmp_path / name
    path.write_text("".join(chunks), encoding="utf-8")
    return path
```

`LICENSE`: the MIT licence text with `Copyright (c) 2026 Kinnari Sharma`.

`README.md` (stub, replaced in Task 12):
```markdown
# accountscope

Inventory every organisation that holds an account for you from a mailbox export,
tagged with which of your addresses each one uses. Zero network. Work in progress.
```

`CHANGELOG.md`:
```markdown
# Changelog

## Unreleased
- Initial development.
```

`.gitignore`:
```
__pycache__/
*.egg-info/
build/
dist/
.pytest_cache/
*.tmp
accountscope.json
accountscope.html
```

- [ ] **Step 4: Install in editable mode and run the tests**

Run: `cd ~/personal-dev/accountscope && python3 -m pip install -e ".[dev]" -q && python3 -m pytest tests/test_scaffold.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Scaffold accountscope package with network guard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Streaming mbox reader and body text extraction

**Files:**
- Create: `accountscope/mbox.py`
- Test: `tests/test_mbox.py`

**Interfaces:**
- Produces:
  - `class NotAnMbox(Exception)`
  - `@dataclass(frozen=True) Message(key: str, sender: str, sender_name: str, reply_to: str, subject: str, date: datetime | None, recipients: frozenset[str], has_list_unsubscribe: bool)` — all addresses lower-cased.
  - `@dataclass MboxStats(total: int = 0, skipped: int = 0, no_recipients: int = 0)`
  - `check_mbox(path: Path) -> None` raises `NotAnMbox`.
  - `iter_messages(path: Path, stats: MboxStats) -> Iterator[Message]`
  - `strip_html(html: str) -> str`
  - `class BodyReader(path: Path)` with `.text(key: str) -> str` and `.close()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_mbox.py`:
```python
from datetime import timezone
from pathlib import Path

import pytest

from accountscope.mbox import BodyReader, MboxStats, NotAnMbox, check_mbox, iter_messages, strip_html
from tests.helpers import make_mbox

PLAIN = (
    "From: Example Bank <alerts@example.com>\n"
    "To: Me <me@gmail.com>\n"
    "Cc: other@friend.org\n"
    "Delivered-To: me+bank@gmail.com\n"
    "Reply-To: support@example.com\n"
    "Date: Tue, 03 Sep 2024 10:15:00 +0530\n"
    "Subject: Your statement is ready\n"
    "List-Unsubscribe: <mailto:unsub@example.com>\n"
    "Content-Type: text/plain; charset=utf-8\n"
    "\n"
    "Your card ending 4421 was charged.\n"
)

HTML_ONLY = (
    "From: shop@store.example\n"
    "To: me@gmail.com\n"
    "Subject: =?utf-8?q?Order_=23123_confirmed?=\n"
    "Content-Type: text/html; charset=utf-8\n"
    "\n"
    "<html><body><style>p{}</style><p>Thanks for your order!</p><p>Ship to:<br>12 High St<br>London SW1A 1AA</p></body></html>\n"
)

MALFORMED = "This is not a message at all\n"


def test_check_mbox_rejects_non_mbox(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello\n")
    with pytest.raises(NotAnMbox):
        check_mbox(p)


def test_iter_messages_parses_headers_and_lowercases_addresses(tmp_path):
    path = make_mbox(tmp_path, [PLAIN])
    stats = MboxStats()
    msgs = list(iter_messages(path, stats))
    assert stats.total == 1 and stats.skipped == 0
    m = msgs[0]
    assert m.sender == "alerts@example.com"
    assert m.sender_name == "Example Bank"
    assert m.reply_to == "support@example.com"
    assert m.subject == "Your statement is ready"
    assert m.recipients == frozenset({"me@gmail.com", "other@friend.org", "me+bank@gmail.com"})
    assert m.has_list_unsubscribe is True
    assert m.date is not None and m.date.tzinfo == timezone.utc
    assert m.date.isoformat() == "2024-09-03T04:45:00+00:00"


def test_iter_messages_decodes_encoded_subject_and_counts_no_recipients(tmp_path):
    no_rcpt = "From: x@y.org\nSubject: hi\n\nbody\n"
    path = make_mbox(tmp_path, [HTML_ONLY, no_rcpt])
    stats = MboxStats()
    msgs = list(iter_messages(path, stats))
    assert msgs[0].subject == "Order #123 confirmed"
    assert msgs[0].date is None
    assert stats.no_recipients == 1


def test_strip_html_drops_style_and_keeps_line_breaks():
    text = strip_html("<style>p{}</style><p>Thanks!</p><p>Ship to:<br>12 High St<br>London SW1A 1AA</p>")
    assert "p{}" not in text
    assert "Thanks!" in text
    assert "12 High St\nLondon SW1A 1AA" in text


def test_body_reader_prefers_plain_and_falls_back_to_html(tmp_path):
    path = make_mbox(tmp_path, [PLAIN, HTML_ONLY])
    stats = MboxStats()
    keys = [m.key for m in iter_messages(path, stats)]
    reader = BodyReader(path)
    try:
        assert "card ending 4421" in reader.text(keys[0])
        assert "Thanks for your order!" in reader.text(keys[1])
        assert reader.text("9999") == ""
    finally:
        reader.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.mbox'`.

- [ ] **Step 3: Implement `accountscope/mbox.py`**

```python
"""Stream messages out of an mbox file without holding more than one in memory."""
from __future__ import annotations

import mailbox
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message as EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator

RECIPIENT_HEADERS = ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To", "X-Envelope-To")
BODY_LIMIT = 200_000


class NotAnMbox(Exception):
    """The file does not start with an mbox 'From ' separator line."""


@dataclass(frozen=True)
class Message:
    key: str
    sender: str
    sender_name: str
    reply_to: str
    subject: str
    date: datetime | None
    recipients: frozenset[str]
    has_list_unsubscribe: bool


@dataclass
class MboxStats:
    total: int = 0
    skipped: int = 0
    no_recipients: int = 0


def _decode(value) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value)))).strip()
    except Exception:
        return str(value).strip()


def _addresses(msg: EmailMessage, headers) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for header in headers:
        raw_values = [_decode(v) for v in msg.get_all(header, [])]
        for name, addr in getaddresses(raw_values):
            addr = addr.strip().lower()
            if "@" in addr:
                pairs.append((name.strip(), addr))
    return pairs


def _parse_date(msg: EmailMessage) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_message(key, msg: EmailMessage) -> Message:
    senders = _addresses(msg, ("From",))
    sender_name, sender = senders[0] if senders else ("", "")
    replies = _addresses(msg, ("Reply-To",))
    recipients = frozenset(addr for _, addr in _addresses(msg, RECIPIENT_HEADERS))
    return Message(
        key=str(key),
        sender=sender,
        sender_name=sender_name,
        reply_to=replies[0][1] if replies else "",
        subject=_decode(msg.get("Subject")),
        date=_parse_date(msg),
        recipients=recipients,
        has_list_unsubscribe=msg.get("List-Unsubscribe") is not None,
    )


def check_mbox(path: Path) -> None:
    with open(path, "rb") as fh:
        head = fh.read(5)
    if head != b"From ":
        raise NotAnMbox(f"{path} does not start with an mbox 'From ' line (starts with {head!r})")


def iter_messages(path: Path, stats: MboxStats) -> Iterator[Message]:
    check_mbox(path)
    box = mailbox.mbox(str(path), create=False)
    try:
        for key in box.iterkeys():
            stats.total += 1
            try:
                message = to_message(key, box.get_message(key))
            except Exception:
                stats.skipped += 1
                continue
            if not message.recipients:
                stats.no_recipients += 1
            yield message
    finally:
        box.close()


class _TextExtractor(HTMLParser):
    BREAKS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def body_text(msg: EmailMessage, limit: int = BODY_LIMIT) -> str:
    plain: list[str] = []
    html: list[str] = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        if part.get_content_disposition() == "attachment":
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        (plain if ctype == "text/plain" else html).append(text)
    if plain:
        return "\n".join(plain)[:limit]
    if html:
        return strip_html("\n".join(html))[:limit]
    return ""


class BodyReader:
    """Opens the mbox once for pass 2 and fetches plain-text bodies by message key."""

    def __init__(self, path: Path) -> None:
        self._box = mailbox.mbox(str(path), create=False)

    def text(self, key: str) -> str:
        try:
            return body_text(self._box.get_message(int(key)))
        except Exception:
            return ""

    def close(self) -> None:
        self._box.close()
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_mbox.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add accountscope/mbox.py tests/test_mbox.py
git commit -m "Add streaming mbox reader and body text extraction

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Self-address inference

**Files:**
- Create: `accountscope/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Produces:
  - `canonical(address: str) -> str` — lower-case, plus-tag removed.
  - `@dataclass SelfAddress(address: str, aliases: list[str], messages: int, declared: bool)` with `.to_dict()`.
  - `class SelfDetector` with `.add(recipients: Iterable[str]) -> None`, `.resolve(total_messages: int, me: Iterable[str] = (), not_me: Iterable[str] = ()) -> list[SelfAddress]`; class constants `SHARE = 0.02`, `FLOOR = 200`.

- [ ] **Step 1: Write the failing tests**

`tests/test_identity.py`:
```python
from accountscope.identity import SelfDetector, canonical


def test_canonical_lowercases_and_strips_plus_tag():
    assert canonical("Me+Shop@Gmail.com") == "me@gmail.com"
    assert canonical("plain@example.org") == "plain@example.org"
    assert canonical("weird+@example.org") == "weird@example.org"


def test_resolve_by_share_and_floor():
    d = SelfDetector()
    for _ in range(300):
        d.add({"me@gmail.com"})
    for _ in range(50):
        d.add({"me+shop@gmail.com", "friend@x.org"})
    for _ in range(10):
        d.add({"rare@y.org"})
    resolved = d.resolve(total_messages=360)
    addresses = {s.address for s in resolved}
    assert "me@gmail.com" in addresses          # 350 >= FLOOR
    assert "friend@x.org" in addresses         # 50/360 = 13.9% >= SHARE
    assert "rare@y.org" not in addresses       # 10/360 = 2.8%? no: below FLOOR and 10/360=2.7% >= 2% -> included; use 5
    me = next(s for s in resolved if s.address == "me@gmail.com")
    assert me.aliases == ["me+shop@gmail.com"]
    assert me.messages == 350
    assert me.declared is False


def test_share_threshold_edge():
    d = SelfDetector()
    for _ in range(1000):
        d.add({"me@gmail.com"})
    for _ in range(19):
        d.add({"almost@x.org"})
    for _ in range(20):
        d.add({"exactly@x.org"})
    addresses = {s.address for s in d.resolve(total_messages=1000)}
    assert "almost@x.org" not in addresses     # 1.9%
    assert "exactly@x.org" in addresses        # 2.0%


def test_me_and_not_me_override_inference():
    d = SelfDetector()
    for _ in range(300):
        d.add({"me@gmail.com", "list@team.org"})
    resolved = d.resolve(total_messages=300, me=["Old@ISP.net"], not_me=["list@team.org"])
    by = {s.address: s for s in resolved}
    assert "list@team.org" not in by
    assert by["old@isp.net"].declared is True and by["old@isp.net"].messages == 0
    assert by["me@gmail.com"].declared is False
```

Note for the implementer: the first test's `rare@y.org` comment shows the arithmetic; with 10 of 360 messages (2.7%) the address DOES qualify by share. Change the loop to `range(5)` (1.4%) so the assertion is correct. Final test code uses `range(5)`.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.identity'`.

- [ ] **Step 3: Implement `accountscope/identity.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_identity.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add accountscope/identity.py tests/test_identity.py
git commit -m "Infer the user's own addresses from recipient headers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Bundled data, refresh script, and organisation identity

**Files:**
- Create: `scripts/refresh_data.py`, `accountscope/data/rules.json`, `accountscope/data/public_suffix_list.dat`, `accountscope/data/justdeleteme.json`, `accountscope/orgs.py`
- Test: `tests/test_orgs.py`

**Interfaces:**
- Produces:
  - `registrable_domain(host: str) -> str`
  - `@dataclass(frozen=True) OrgIdentity(key: str, name: str, via_relay: bool)`
  - `identify(sender: str, sender_name: str, reply_to: str, relays: frozenset[str]) -> OrgIdentity`
  - `load_rules() -> dict` (in `accountscope/classify.py`, Task 5, but `orgs.py` reads relays from the same file via `accountscope.data`); to avoid a forward dependency, `orgs.py` exposes `load_relays() -> frozenset[str]`.
  - `accountscope/data/rules.json` keys: `relays` (list), `types` (ordered list of `{type, any, needs_digits?}`), `translations` (type → list), `categories` (category → list of keywords).
  - `accountscope/data/justdeleteme.json`: `{ "<registrable domain>": {"name": str, "url": str, "difficulty": str} }`.

- [ ] **Step 1: Write the refresh script and fetch the data (one-time, network allowed here only)**

`scripts/refresh_data.py`:
```python
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
```

Before running, confirm the JustDeleteMe raw path by opening https://github.com/jdm-contrib/jdm and locating `_data/sites.json`; if the file has moved, update `JDM_URL` to the current raw URL. Then write `accountscope/orgs.py` (Step 3) FIRST, because `refresh_jdm` imports `registrable_domain`, and run:

Run: `python3 scripts/refresh_data.py`
Expected: two lines with counts in the thousands (PSL ~9,000+ rules; JustDeleteMe ~1,500+ domains). Confirm with `head -3 accountscope/data/public_suffix_list.dat` and `python3 -c "import json;d=json.load(open('accountscope/data/justdeleteme.json'));print(len(d), d.get('facebook.com'))"`.

- [ ] **Step 2: Write `accountscope/data/rules.json`**

```json
{
  "relays": [
    "sendgrid.net", "mailchimp.com", "mcsv.net", "rsgsv.net", "mailgun.org", "mailgun.net",
    "amazonses.com", "postmarkapp.com", "sparkpostmail.com", "constantcontact.com",
    "hubspotemail.net", "klaviyomail.com", "braze.com", "iterable.com", "exacttarget.com",
    "cmail19.com", "cmail20.com", "sendinblue.com", "brevo.com", "activehosted.com",
    "customeriomail.com", "mandrillapp.com", "intercom-mail.com", "mailjet.com", "sendpulse.com",
    "emailsrvr.com", "mailanyone.net", "e.customeriomail.com"
  ],
  "types": [
    {"type": "otp", "any": ["code", "otp", "verification", "verify", "passcode", "one-time", "one time"], "needs_digits": true},
    {"type": "verify", "any": ["verify", "verification", "confirm your", "activate", "validate", "confirm email"]},
    {"type": "reset", "any": ["reset", "forgot", "new password", "change your password"]},
    {"type": "signup", "any": ["welcome", "thanks for signing up", "thank you for signing up", "account created", "you're in", "get started", "registration"]},
    {"type": "receipt", "any": ["receipt", "order", "invoice", "payment received", "thank you for your purchase", "your purchase", "payment confirmation"]},
    {"type": "statement", "any": ["statement", "bill is ready", "e-statement", "monthly summary", "payslip", "your bill"]},
    {"type": "notice", "any": ["shipped", "delivery", "on its way", "billing update", "autopay", "payment due", "renewal", "subscription", "delivered"]}
  ],
  "translations": {
    "otp": ["código", "codigo", "कोड", "ओटीपी", "verifizierung", "code de vérification"],
    "verify": ["confirme", "confirmez", "bestätigen", "verifique", "सत्यापित"],
    "reset": ["contraseña", "senha", "passwort", "mot de passe", "पासवर्ड"],
    "signup": ["bienvenido", "bem-vindo", "willkommen", "bienvenue", "स्वागत"],
    "receipt": ["recibo", "pedido", "rechnung", "reçu", "commande", "रसीद", "ऑर्डर"],
    "statement": ["extracto", "extrato", "kontoauszug", "relevé", "स्टेटमेंट"],
    "notice": ["enviado", "livraison", "versand", "entrega", "डिलीवरी"]
  },
  "categories": {
    "government": ["gov", "nic.in", "hmrc", "irs.", "passport", "council", "dmv", "electoral", "municipal", "uidai", "incometax"],
    "finance": ["bank", "card", "credit", "pay", "wallet", "invest", "fund", "insurance", "loan", "upi", "capital", "finance", "mutual", "pension", "tax", "zerodha", "groww", "paytm", "phonepe"],
    "health": ["health", "clinic", "hospital", "pharmacy", "doctor", "dental", "medical", "lab", "apollo", "practo"],
    "utilities": ["electric", "power", "gas", "water", "energy", "broadband", "fiber", "utility", "bescom", "tata power"],
    "telecom": ["mobile", "telecom", "airtel", "jio", "vodafone", "verizon", "t-mobile", "att.com", "sim", "vi.com"],
    "travel": ["airline", "airways", "flight", "hotel", "booking", "rail", "train", "travel", "uber", "ola", "irctc", "makemytrip", "indigo"],
    "work": ["payroll", "workday", "slack", "github", "atlassian", "jira", "notion", "zoom", "deel", "linkedin"],
    "social": ["facebook", "instagram", "twitter", "x.com", "reddit", "discord", "meta", "snapchat", "tiktok"],
    "shopping": ["shop", "store", "amazon", "flipkart", "market", "mall", "cart", "myntra", "swiggy", "zomato", "bigbasket"]
  }
}
```

- [ ] **Step 3: Write the failing tests**

`tests/test_orgs.py`:
```python
from accountscope.orgs import OrgIdentity, identify, load_relays, registrable_domain


def test_registrable_domain_handles_multi_label_suffixes():
    assert registrable_domain("alerts.example.co.uk") == "example.co.uk"
    assert registrable_domain("mail.example.com") == "example.com"
    assert registrable_domain("example.com") == "example.com"
    assert registrable_domain("localhost") == "localhost"
    assert registrable_domain("Foo.Example.COM.") == "example.com"


def test_registrable_domain_known_public_suffixes():
    assert registrable_domain("something.github.io") == "something.github.io"
    assert registrable_domain("co.uk") == "co.uk"


def test_identify_plain_sender():
    ident = identify("alerts@mail.example.com", "Example Bank", "", load_relays())
    assert ident == OrgIdentity(key="example.com", name="Example Bank", via_relay=False)


def test_identify_relay_uses_reply_to_domain():
    ident = identify("bounce@em1234.sendgrid.net", "Acme Shop", "help@acme.example", load_relays())
    assert ident.key == "acme.example" and ident.via_relay is True and ident.name == "Acme Shop"


def test_identify_relay_without_reply_to_slugs_display_name():
    ident = identify("bounce@mcsv.net", "Weekly Digest!", "", load_relays())
    assert ident == OrgIdentity(key="weekly-digest", name="Weekly Digest!", via_relay=True)


def test_identify_missing_sender():
    ident = identify("", "", "", load_relays())
    assert ident.key == "unknown"
```

- [ ] **Step 4: Run to verify failure**

Run: `python3 -m pytest tests/test_orgs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.orgs'`.

- [ ] **Step 5: Implement `accountscope/orgs.py`** (write this before running the refresh script in Step 1)

```python
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
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


def _domain_of(address: str) -> str:
    return registrable_domain(address.rsplit("@", 1)[1]) if "@" in address else ""


def identify(sender: str, sender_name: str, reply_to: str, relays: frozenset[str]) -> OrgIdentity:
    domain = _domain_of(sender)
    if domain and domain in relays:
        reply_domain = _domain_of(reply_to)
        if reply_domain and reply_domain not in relays:
            return OrgIdentity(reply_domain, sender_name or reply_domain, True)
        return OrgIdentity(_slug(sender_name) if sender_name else domain, sender_name or domain, True)
    key = domain or "unknown"
    return OrgIdentity(key, sender_name or key, False)
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/test_orgs.py -v`
Expected: 6 passed. (The `github.io` assertion depends on the real PSL listing `github.io`; it does.)

- [ ] **Step 7: Commit**

```bash
git add scripts/refresh_data.py accountscope/data accountscope/orgs.py tests/test_orgs.py
git commit -m "Bundle public-suffix list and JustDeleteMe data; add organisation identity

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Message-type classification

**Files:**
- Create: `accountscope/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Produces: `TRANSACTIONAL: frozenset[str]` = `{"otp","verify","reset","signup","receipt","statement","notice"}`; `load_rules() -> dict`; `classify(subject: str, has_list_unsubscribe: bool, rules: dict | None = None) -> str` returning one of the seven transactional types, `"marketing"`, or `"other"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_classify.py`:
```python
import pytest

from accountscope.classify import TRANSACTIONAL, classify, load_rules


@pytest.mark.parametrize(
    "subject,unsub,expected",
    [
        ("Your verification code is 483920", False, "otp"),
        ("123456 is your OTP", False, "otp"),
        ("Verify your email address", False, "verify"),
        ("Please confirm your account", False, "verify"),
        ("Reset your password", False, "reset"),
        ("Welcome to Example!", False, "signup"),
        ("Your receipt from Example", False, "receipt"),
        ("Order #4521 confirmed", False, "receipt"),
        ("Your statement is ready", False, "statement"),
        ("Your order has shipped", False, "notice"),
        ("Autopay reminder", False, "notice"),
        ("Big spring sale!", True, "marketing"),
        ("Big spring sale!", False, "other"),
        ("Su código es 998877", False, "otp"),
        ("Bem-vindo à Loja", False, "signup"),
        ("Ihre Rechnung", False, "receipt"),
        ("आपका ओटीपी 4455 है", False, "otp"),
    ],
)
def test_classify(subject, unsub, expected):
    assert classify(subject, unsub) == expected


def test_transactional_set():
    assert TRANSACTIONAL == frozenset({"otp", "verify", "reset", "signup", "receipt", "statement", "notice"})
    assert "marketing" not in TRANSACTIONAL


def test_rules_load_and_are_ordered():
    rules = load_rules()
    assert [r["type"] for r in rules["types"]] == ["otp", "verify", "reset", "signup", "receipt", "statement", "notice"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.classify'`.

- [ ] **Step 3: Implement `accountscope/classify.py`**

```python
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
    rules = rules or load_rules()
    text = subject.lower()
    translations = rules.get("translations", {})
    for rule in rules["types"]:
        words = list(rule["any"]) + list(translations.get(rule["type"], []))
        if any(word in text for word in words):
            if rule.get("needs_digits") and not _DIGITS.search(text):
                continue
            return rule["type"]
    return "marketing" if has_list_unsubscribe else "other"
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_classify.py -v`
Expected: all passed (19 tests).

- [ ] **Step 5: Commit**

```bash
git add accountscope/classify.py tests/test_classify.py
git commit -m "Classify message types from subject and headers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Inventory model and aggregation

**Files:**
- Create: `accountscope/inventory.py`
- Test: `tests/test_inventory.py`

**Interfaces:**
- Consumes: `Message` (Task 2), `canonical` (Task 3), `OrgIdentity` (Task 4), `TRANSACTIONAL` (Task 5).
- Produces:
  - `PASS2_CAP = 25`
  - `@dataclass Fact(fact: str, value: str, evidence: str, seen: str, confidence: str, inferred: bool = True)` with `.to_dict()`.
  - `@dataclass Organisation(key, ...)` with properties `.name`, `.marketing_only`, fields `types: Counter`, `first_seen`, `last_seen`, `writes_to: dict[str, dict]`, `holds: list[Fact]`, `pass2: list[tuple[str, str]]` (date_iso, key), `delete: dict | None`, `category: str`, `via_relay: bool`, and `.to_dict()`.
  - `@dataclass Inventory(source: dict, self_addresses: list[SelfAddress], organisations: list[Organisation])` with `.to_dict()` and `.transactional_count(org)`.
  - `class Aggregator` with `.add(message: Message, identity: OrgIdentity, msg_type: str) -> None` and `.finish(source: dict, self_addresses: list[SelfAddress]) -> Inventory`.
  - `categorise(org: Organisation, categories: dict) -> str`; `load_justdeleteme() -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/test_inventory.py`:
```python
from datetime import datetime, timezone

from accountscope.identity import SelfAddress
from accountscope.inventory import PASS2_CAP, Aggregator, Fact, Organisation, categorise
from accountscope.mbox import Message
from accountscope.orgs import OrgIdentity


def msg(key, sender, name, subject, date, recipients, unsub=False):
    return Message(key=str(key), sender=sender, sender_name=name, reply_to="", subject=subject,
                   date=datetime(*date, tzinfo=timezone.utc), recipients=frozenset(recipients),
                   has_list_unsubscribe=unsub)


def test_aggregator_builds_writes_to_only_for_self_addresses():
    agg = Aggregator()
    bank = OrgIdentity("example.com", "Example Bank", False)
    agg.add(msg(1, "alerts@example.com", "Example Bank", "Statement", (2019, 1, 4), {"old@isp.net"}), bank, "statement")
    agg.add(msg(2, "alerts@example.com", "Example Bank", "Statement", (2024, 9, 3), {"me+bank@gmail.com", "friend@x.org"}), bank, "statement")
    agg.add(msg(3, "news@example.com", "Example Bank", "Sale", (2024, 9, 5), {"me@gmail.com"}, unsub=True), bank, "marketing")
    inv = agg.finish({"path": "x"}, [SelfAddress("me@gmail.com", ["me+bank@gmail.com"], 2, False), SelfAddress("old@isp.net", [], 1, True)])
    org = inv.organisations[0]
    assert org.key == "example.com" and org.name == "Example Bank"
    assert org.sender_addresses == {"alerts@example.com", "news@example.com"}
    assert org.types == {"statement": 2, "marketing": 1}
    assert org.first_seen == "2019-01-04" and org.last_seen == "2024-09-05"
    assert org.writes_to == {
        "me@gmail.com": {"last": "2024-09-05", "count": 2},
        "old@isp.net": {"last": "2019-01-04", "count": 1},
    }
    assert "friend@x.org" not in org.writes_to
    assert org.marketing_only is False
    assert [k for _, k in org.pass2] == ["2", "1"]          # transactional only, most recent first


def test_pass2_is_capped_to_most_recent():
    agg = Aggregator()
    ident = OrgIdentity("shop.example", "Shop", False)
    for i in range(60):
        agg.add(msg(i, "a@shop.example", "Shop", "Receipt", (2020, 1, 1 + i % 28), {"me@gmail.com"}), ident, "receipt")
    inv = agg.finish({}, [SelfAddress("me@gmail.com", [], 60, False)])
    org = inv.organisations[0]
    assert len(org.pass2) == PASS2_CAP
    assert org.pass2[0][0] >= org.pass2[-1][0]


def test_marketing_only_and_name_by_frequency():
    agg = Aggregator()
    agg.add(msg(1, "n@news.example", "Newsletter", "Sale", (2024, 1, 1), {"me@gmail.com"}, True), OrgIdentity("news.example", "Newsletter", False), "marketing")
    agg.add(msg(2, "n@news.example", "The Newsletter", "Sale", (2024, 1, 2), {"me@gmail.com"}, True), OrgIdentity("news.example", "The Newsletter", False), "marketing")
    agg.add(msg(3, "n@news.example", "The Newsletter", "Sale", (2024, 1, 3), {"me@gmail.com"}, True), OrgIdentity("news.example", "The Newsletter", False), "marketing")
    inv = agg.finish({}, [SelfAddress("me@gmail.com", [], 3, False)])
    org = inv.organisations[0]
    assert org.marketing_only is True and org.name == "The Newsletter" and org.pass2 == []


def test_categorise_prefers_government_then_finance():
    cats = {"government": ["gov"], "finance": ["bank"], "shopping": ["shop"]}
    assert categorise(Organisation(key="tax.gov.in"), cats) == "government"
    assert categorise(Organisation(key="mybank.com"), cats) == "finance"
    org = Organisation(key="acme.example")
    org.types["statement"] = 3
    assert categorise(org, cats) == "finance"
    assert categorise(Organisation(key="acme.example"), cats) == "other"


def test_to_dict_shape_and_no_third_party_data():
    agg = Aggregator()
    agg.add(msg(1, "alerts@example.com", "Example Bank", "Statement", (2024, 9, 3), {"me@gmail.com", "friend@x.org"}), OrgIdentity("example.com", "Example Bank", False), "statement")
    inv = agg.finish({"path": "t.mbox", "messages": 1, "skipped": 0, "date_range": ["2024-09-03", "2024-09-03"]},
                     [SelfAddress("me@gmail.com", [], 1, False)])
    inv.organisations[0].holds = [Fact("card", "ending 4421", "your card ending 4421", "2024-09-03", "medium")]
    data = inv.to_dict()
    assert data["schema"] == "accountscope/1"
    assert data["self"] == [{"address": "me@gmail.com", "aliases": [], "messages": 1, "declared": False}]
    org = data["organisations"][0]
    assert set(org) == {"key", "name", "sender_addresses", "types", "marketing_only", "first_seen", "last_seen",
                        "writes_to", "holds", "delete", "category", "via_relay"}
    assert org["writes_to"] == [{"address": "me@gmail.com", "last": "2024-09-03", "count": 1}]
    assert org["holds"][0] == {"fact": "card", "value": "ending 4421", "evidence": "your card ending 4421",
                               "seen": "2024-09-03", "confidence": "medium", "inferred": True}
    assert "friend@x.org" not in str(data)
    assert "Statement" not in str(data)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_inventory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.inventory'`.

- [ ] **Step 3: Implement `accountscope/inventory.py`**

```python
"""The in-memory model: one Organisation per sender organisation, aggregated over the mailbox."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources

from accountscope.classify import TRANSACTIONAL, load_rules
from accountscope.identity import SelfAddress, canonical
from accountscope.mbox import Message
from accountscope.orgs import OrgIdentity

SCHEMA = "accountscope/1"
PASS2_CAP = 25
CATEGORY_ORDER = ["government", "finance", "health", "utilities", "telecom", "travel", "work", "social", "shopping"]


@dataclass
class Fact:
    fact: str
    value: str
    evidence: str
    seen: str
    confidence: str
    inferred: bool = True

    def to_dict(self) -> dict:
        return {"fact": self.fact, "value": self.value, "evidence": self.evidence,
                "seen": self.seen, "confidence": self.confidence, "inferred": self.inferred}


@dataclass
class Organisation:
    key: str
    via_relay: bool = False
    names: Counter = field(default_factory=Counter)
    sender_addresses: set = field(default_factory=set)
    types: Counter = field(default_factory=Counter)
    first_seen: str | None = None
    last_seen: str | None = None
    recipients: dict = field(default_factory=dict)      # canonical address -> {"last": date, "count": n}; pruned at finish
    writes_to: dict = field(default_factory=dict)       # self address -> {"last": date, "count": n}
    holds: list = field(default_factory=list)           # list[Fact]
    pass2: list = field(default_factory=list)           # list[(date_iso, key)]
    delete: dict | None = None
    category: str = "other"

    @property
    def name(self) -> str:
        return self.names.most_common(1)[0][0] if self.names else self.key

    @property
    def marketing_only(self) -> bool:
        return "marketing" in self.types and not (set(self.types) & TRANSACTIONAL)

    @property
    def transactional_count(self) -> int:
        return sum(n for t, n in self.types.items() if t in TRANSACTIONAL)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "sender_addresses": sorted(self.sender_addresses),
            "types": dict(sorted(self.types.items())),
            "marketing_only": self.marketing_only,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "writes_to": [{"address": a, "last": w["last"], "count": w["count"]}
                          for a, w in sorted(self.writes_to.items(), key=lambda kv: (kv[1]["last"] or ""), reverse=True)],
            "holds": [f.to_dict() for f in self.holds],
            "delete": self.delete,
            "category": self.category,
            "via_relay": self.via_relay,
        }


@dataclass
class Inventory:
    source: dict
    self_addresses: list
    organisations: list

    def to_dict(self) -> dict:
        ordered = sorted(self.organisations, key=lambda o: (-o.transactional_count, -sum(o.types.values()), o.key))
        return {
            "schema": SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": self.source,
            "self": [s.to_dict() for s in self.self_addresses],
            "organisations": [o.to_dict() for o in ordered],
        }


@lru_cache(maxsize=1)
def load_justdeleteme() -> dict:
    text = resources.files("accountscope.data").joinpath("justdeleteme.json").read_text(encoding="utf-8")
    return json.loads(text)


def categorise(org: Organisation, categories: dict) -> str:
    haystack = (org.key + " " + org.name).lower()
    for category in CATEGORY_ORDER:
        if any(word in haystack for word in categories.get(category, [])):
            return category
    if org.types.get("statement"):
        return "finance"
    return "other"


class Aggregator:
    def __init__(self) -> None:
        self.orgs: dict[str, Organisation] = {}

    def add(self, message: Message, identity: OrgIdentity, msg_type: str) -> None:
        org = self.orgs.get(identity.key)
        if org is None:
            org = self.orgs[identity.key] = Organisation(key=identity.key, via_relay=identity.via_relay)
        if identity.name:
            org.names[identity.name] += 1
        if message.sender:
            org.sender_addresses.add(message.sender)
        org.types[msg_type] += 1
        day = message.date.date().isoformat() if message.date else None
        if day:
            org.first_seen = day if org.first_seen is None else min(org.first_seen, day)
            org.last_seen = day if org.last_seen is None else max(org.last_seen, day)
        for raw in message.recipients:
            entry = org.recipients.setdefault(canonical(raw), {"last": None, "count": 0})
            entry["count"] += 1
            if day and (entry["last"] is None or day > entry["last"]):
                entry["last"] = day
        if msg_type in TRANSACTIONAL:
            org.pass2.append((day or "", message.key))
            if len(org.pass2) > PASS2_CAP * 2:
                org.pass2.sort(reverse=True)
                del org.pass2[PASS2_CAP:]

    def finish(self, source: dict, self_addresses: list[SelfAddress]) -> Inventory:
        self_set = {s.address for s in self_addresses}
        categories = load_rules().get("categories", {})
        jdm = load_justdeleteme()
        for org in self.orgs.values():
            org.writes_to = {a: w for a, w in org.recipients.items() if a in self_set}
            org.recipients = {}
            org.pass2.sort(reverse=True)
            del org.pass2[PASS2_CAP:]
            org.delete = jdm.get(org.key)
            org.category = categorise(org, categories)
        return Inventory(source, list(self_addresses), list(self.orgs.values()))
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_inventory.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add accountscope/inventory.py tests/test_inventory.py
git commit -m "Add inventory model and aggregation with self-address filtering

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Held-fact extraction (pass 2)

**Files:**
- Create: `accountscope/facts.py`
- Test: `tests/test_facts.py`

**Interfaces:**
- Consumes: `Fact` (Task 6).
- Produces: `@dataclass(frozen=True) FactHit(fact: str, value: str, evidence: str, seen: str)`; `extract_facts(text: str, seen: str) -> list[FactHit]`; `merge_facts(hits: Iterable[FactHit]) -> list[Fact]`; `EVIDENCE_WIDTH = 120`.

- [ ] **Step 1: Write the failing tests**

`tests/test_facts.py`:
```python
from accountscope.facts import EVIDENCE_WIDTH, FactHit, extract_facts, merge_facts


def test_card_ending_is_masked_and_evidenced():
    hits = extract_facts("Hi. Your Visa card ending in 4421 was charged $12.00 today.", "2024-09-01")
    assert hits == [FactHit("card", "ending 4421", "Your Visa card ending in 4421 was charged $12.00 today.", "2024-09-01")]


def test_card_last_four_digits_variant():
    hits = extract_facts("We charged the card with last 4 digits 9876.", "2024-01-01")
    assert hits[0].fact == "card" and hits[0].value == "ending 9876"


def test_phone_masked_tail():
    hits = extract_facts("We sent a code to your phone number ******1234. Enter it to continue.", "2024-02-02")
    assert hits == [FactHit("phone", "ending 1234", "We sent a code to your phone number ******1234. Enter it to continue.", "2024-02-02")]


def test_address_line_after_cue():
    text = "Thanks for your order!\nShipping address:\nKinnari S\n12 High St\nLondon SW1A 1AA\nUnited Kingdom\n"
    hits = extract_facts(text, "2024-03-03")
    assert [h.fact for h in hits] == ["address"]
    assert hits[0].value == "London SW1A 1AA"


def test_no_false_positives_on_marketing_copy():
    text = "Get 20% off with code SAVE20 on orders over $50. Free delivery on 100000 items!"
    assert extract_facts(text, "2024-04-04") == []


def test_evidence_is_capped():
    text = "card ending 1111 " + "x" * 500
    hits = extract_facts(text, "2024-05-05")
    assert len(hits[0].evidence) <= EVIDENCE_WIDTH


def test_merge_confidence_by_distinct_dates():
    hits = [
        FactHit("card", "ending 4421", "e1", "2024-01-01"),
        FactHit("card", "ending 4421", "e2", "2024-06-01"),
        FactHit("card", "ending 9999", "e3", "2024-06-01"),
        FactHit("phone", "ending 1234", "e4", "2024-06-01"),
        FactHit("phone", "ending 1234", "e5", "2024-06-01"),
    ]
    facts = {(f.fact, f.value): f for f in merge_facts(hits)}
    assert facts[("card", "ending 4421")].confidence == "high"
    assert facts[("card", "ending 4421")].evidence == "e2" and facts[("card", "ending 4421")].seen == "2024-06-01"
    assert facts[("card", "ending 9999")].confidence == "medium"
    assert facts[("phone", "ending 1234")].confidence == "medium"   # same date twice
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_facts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.facts'`.

- [ ] **Step 3: Implement `accountscope/facts.py`**

```python
"""Pass-2 extractors: what an organisation holds about the user, from transactional message text."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from accountscope.inventory import Fact

EVIDENCE_WIDTH = 120

CARD = re.compile(
    r"(?:card|visa|mastercard|amex|debit|credit)[^.\n]{0,40}?"
    r"(?:ending(?: in)?|last (?:4|four) digits)[^0-9\n]{0,10}(\d{4})",
    re.IGNORECASE,
)
PHONE = re.compile(
    r"(?:code|text|sms|message)[^.\n]{0,60}?(?:phone|mobile|number)[^0-9*x•\n]{0,20}([0-9*x•]{6,})",
    re.IGNORECASE,
)
ADDRESS_CUE = re.compile(r"(?:ship(?:ping)?|deliver(?:y)?|billing)\s+address\s*:?", re.IGNORECASE)
POSTCODE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}"      # UK
    r"|\d{5}(?:-\d{4})?"                          # US ZIP
    r"|\d{6}"                                     # Indian PIN
    r"|\d{4})\b"                                  # 4-digit (AU, NZ, AT, CH, BE, DK...)
)


@dataclass(frozen=True)
class FactHit:
    fact: str
    value: str
    evidence: str
    seen: str


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - 30)
    window = text[left:left + EVIDENCE_WIDTH]
    window = window.replace("\n", " ").strip()
    if end - left > EVIDENCE_WIDTH:
        window = text[start:start + EVIDENCE_WIDTH].replace("\n", " ").strip()
    return window[:EVIDENCE_WIDTH]


def extract_facts(text: str, seen: str) -> list[FactHit]:
    hits: list[FactHit] = []
    for m in CARD.finditer(text):
        hits.append(FactHit("card", f"ending {m.group(1)}", _snippet(text, m.start(), m.end()), seen))
    for m in PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) < 2:
            continue
        hits.append(FactHit("phone", f"ending {digits[-4:]}", _snippet(text, m.start(), m.end()), seen))
    for m in ADDRESS_CUE.finditer(text):
        window = text[m.end(): m.end() + 300]
        lines = [line.strip() for line in window.splitlines() if line.strip()][:4]
        for line in lines:
            if len(line) < 80 and POSTCODE.search(line) and re.search(r"[A-Za-z]", line):
                hits.append(FactHit("address", line, _snippet(text, m.start(), m.start() + len(line)), seen))
                break
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
```

- [ ] **Step 4: Run the tests; adjust the snippet helper if the exact-evidence assertions fail**

Run: `python3 -m pytest tests/test_facts.py -v`
Expected: 7 passed. The first and third tests assert the evidence equals the full sentence because the sentence is under 120 characters and starts within 30 characters of the match; if `_snippet` returns a substring instead, fix `_snippet` so that when `start - 30 <= 0` the window starts at 0.

- [ ] **Step 5: Commit**

```bash
git add accountscope/facts.py tests/test_facts.py
git commit -m "Extract held facts (card, phone, address) with evidence and confidence

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Terminal summary, atomic JSON, CSV

**Files:**
- Create: `accountscope/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `Inventory` (Task 6).
- Produces: `write_json(data: dict, path: Path) -> None` (atomic); `write_csv(data: dict, path: Path) -> None`; `render_summary(data: dict, stats_extra: dict, outputs: list[Path]) -> str` where `data` is `Inventory.to_dict()` and `stats_extra` has `skipped`, `no_recipients`, `body_failures`.

- [ ] **Step 1: Write the failing tests**

`tests/test_report.py`:
```python
import csv
import json

from accountscope.report import render_summary, write_csv, write_json

DATA = {
    "schema": "accountscope/1",
    "generated_at": "2026-10-02T09:14:00+00:00",
    "source": {"path": "takeout.mbox", "messages": 1000, "skipped": 3, "date_range": ["2014-03-02", "2026-09-30"]},
    "self": [{"address": "me@gmail.com", "aliases": ["me+shop@gmail.com"], "messages": 990, "declared": False}],
    "organisations": [
        {"key": "example.com", "name": "Example Bank", "sender_addresses": ["alerts@example.com"],
         "types": {"otp": 42, "statement": 96, "marketing": 12}, "marketing_only": False,
         "first_seen": "2016-05-11", "last_seen": "2026-09-28",
         "writes_to": [{"address": "me@gmail.com", "last": "2026-09-28", "count": 150}],
         "holds": [{"fact": "card", "value": "ending 4421", "evidence": "e", "seen": "2026-09-01", "confidence": "high", "inferred": True}],
         "delete": {"name": "Example", "url": "https://example.com/close", "difficulty": "hard"},
         "category": "finance", "via_relay": False},
        {"key": "news.example", "name": "Newsletter", "sender_addresses": ["n@news.example"],
         "types": {"marketing": 30}, "marketing_only": True, "first_seen": "2020-01-01", "last_seen": "2026-01-01",
         "writes_to": [{"address": "me@gmail.com", "last": "2026-01-01", "count": 30}],
         "holds": [], "delete": None, "category": "other", "via_relay": False},
    ],
}


def test_write_json_is_atomic_and_round_trips(tmp_path):
    out = tmp_path / "accountscope.json"
    write_json(DATA, out)
    assert json.loads(out.read_text()) == DATA
    assert not (tmp_path / "accountscope.json.tmp").exists()


def test_write_csv_flattens(tmp_path):
    out = tmp_path / "inv.csv"
    write_csv(DATA, out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["key"] == "example.com"
    assert rows[0]["writes_to"] == "me@gmail.com (2026-09-28)"
    assert rows[0]["holds"] == "card ending 4421 [high]"
    assert rows[0]["delete_url"] == "https://example.com/close"
    assert rows[1]["marketing_only"] == "true"


def test_render_summary_mentions_key_facts(tmp_path):
    text = render_summary(DATA, {"skipped": 3, "no_recipients": 0, "body_failures": 1}, [tmp_path / "a.json", tmp_path / "a.html"])
    assert "messages: 1,000" in text
    assert "me@gmail.com" in text and "--me" in text
    assert "finance" in text
    assert "Example Bank" in text
    assert "skipped" in text and "3" in text
    assert "a.json" in text and "a.html" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.report'`.

- [ ] **Step 3: Implement `accountscope/report.py`**

```python
"""Terminal summary, JSON record and CSV export."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path


def write_json(data: dict, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


CSV_FIELDS = ["key", "name", "category", "first_seen", "last_seen", "marketing_only",
              "types", "writes_to", "holds", "delete_url", "delete_difficulty", "sender_addresses"]


def write_csv(data: dict, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for org in data["organisations"]:
            delete = org.get("delete") or {}
            writer.writerow({
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
            })


def render_summary(data: dict, stats_extra: dict, outputs: list[Path]) -> str:
    src = data["source"]
    orgs = data["organisations"]
    lines = []
    lines.append(f"messages: {src['messages']:,}   skipped: {src.get('skipped', 0):,} malformed, "
                 f"{stats_extra.get('no_recipients', 0):,} without recipients, {stats_extra.get('body_failures', 0):,} bodies unreadable")
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
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_report.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add accountscope/report.py tests/test_report.py
git commit -m "Add terminal summary, atomic JSON write and CSV export

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Self-contained HTML viewer

**Files:**
- Create: `accountscope/viewer.py`
- Test: `tests/test_viewer.py`

**Interfaces:**
- Produces: `render_html(data: dict) -> str` and `write_html(data: dict, path: Path) -> None`. The page embeds the JSON in `<script id="inventory" type="application/json">`, has a `<noscript>` grouped table, and loads no external resource.

- [ ] **Step 1: Write the failing tests**

`tests/test_viewer.py`:
```python
import json
import re

from accountscope.viewer import render_html, write_html
from tests.test_report import DATA


def test_html_embeds_json_and_noscript_table():
    html = render_html(DATA)
    m = re.search(r'<script id="inventory" type="application/json">(.*?)</script>', html, re.S)
    assert m and json.loads(m.group(1)) == DATA
    assert "<noscript>" in html
    assert "Example Bank" in html and "finance" in html
    assert "https://example.com/close" in html


def test_html_has_no_external_resources():
    html = render_html(DATA)
    assert not re.search(r'(src|href)="https?://', html.replace('href="https://example.com/close"', ""))
    assert "<link" not in html


def test_json_embedding_escapes_script_close():
    data = json.loads(json.dumps(DATA))
    data["organisations"][0]["name"] = "Evil </script><script>alert(1)</script>"
    html = render_html(data)
    assert "</script><script>alert" not in html
    assert "<\\/script>" in html


def test_write_html(tmp_path):
    out = tmp_path / "accountscope.html"
    write_html(DATA, out)
    assert out.read_text(encoding="utf-8").lstrip().startswith("<!doctype html>")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_viewer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.viewer'`.

- [ ] **Step 3: Implement `accountscope/viewer.py`**

```python
"""One self-contained HTML file: the inventory, grouped, searchable, readable without JavaScript."""
from __future__ import annotations

import html
import json
from pathlib import Path

CSS = """
:root{--ink:#1a1f1e;--muted:#5c6663;--rule:#d6ddd8;--accent:#0e6b60;--soft:#ddefeb;--bg:#f5f7f4;--card:#fff}
@media(prefers-color-scheme:dark){:root{--ink:#e7ece9;--muted:#9ca69f;--rule:#2a3331;--accent:#57bdac;--soft:#163a35;--bg:#111615;--card:#1a2120}}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 8px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.meta{color:var(--muted);font-size:13px}.tools{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
input[type=search]{flex:1 1 240px;padding:8px 10px;border:1px solid var(--rule);border-radius:6px;background:var(--card);color:var(--ink)}
.chip{border:1px solid var(--rule);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 11px;font-size:13px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--soft);border-color:var(--accent);color:var(--accent)}
table{width:100%;border-collapse:collapse;background:var(--card);font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.wrap{overflow-x:auto;border:1px solid var(--rule);border-radius:6px}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;background:var(--soft);color:var(--accent);font-size:12px;margin:0 4px 2px 0}
.dim{color:var(--muted)}a{color:var(--accent)}tr[hidden]{display:none}
"""

JS = """
(function(){
var data=JSON.parse(document.getElementById('inventory').textContent);
var rows=[].slice.call(document.querySelectorAll('tr[data-key]'));
var q=document.getElementById('q');var chips=[].slice.call(document.querySelectorAll('.chip'));
var addr=document.getElementById('addr');
function apply(){
  var text=q.value.toLowerCase();var active=chips.filter(function(c){return c.getAttribute('aria-pressed')==='true'}).map(function(c){return c.dataset.filter});
  var a=addr.value;
  rows.forEach(function(r){
    var ok=!text||r.textContent.toLowerCase().indexOf(text)>=0;
    if(ok&&active.indexOf('card')>=0)ok=r.dataset.holds.indexOf('card')>=0;
    if(ok&&active.indexOf('phone')>=0)ok=r.dataset.holds.indexOf('phone')>=0;
    if(ok&&active.indexOf('marketing')>=0)ok=r.dataset.marketing==='1';
    if(ok&&a)ok=r.dataset.writes.split('|').indexOf(a)>=0;
    r.hidden=!ok;
  });
  document.querySelectorAll('section').forEach(function(s){s.hidden=!s.querySelector('tr[data-key]:not([hidden])')});
}
q.addEventListener('input',apply);addr.addEventListener('change',apply);
chips.forEach(function(c){c.addEventListener('click',function(){c.setAttribute('aria-pressed',c.getAttribute('aria-pressed')==='true'?'false':'true');apply()})});
document.getElementById('tools').hidden=false;
})();
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _rows(orgs: list[dict]) -> str:
    out = []
    for o in orgs:
        holds = " ".join(f'<span class="tag">{_esc(h["fact"])} {_esc(h["value"])}</span>' for h in o["holds"])
        writes = "<br>".join(f'{_esc(w["address"])} <span class="dim">{_esc(w["last"] or "undated")}</span>' for w in o["writes_to"])
        delete = o.get("delete") or {}
        link = f'<a href="{_esc(delete["url"])}" rel="noopener">delete ({_esc(delete.get("difficulty", ""))})</a>' if delete.get("url") else '<span class="dim">-</span>'
        types = ", ".join(f"{_esc(t)} {n}" for t, n in o["types"].items())
        out.append(
            f'<tr data-key="{_esc(o["key"])}" data-holds="{_esc(" ".join(h["fact"] for h in o["holds"]))}" '
            f'data-marketing="{1 if o["marketing_only"] else 0}" data-writes="{_esc("|".join(w["address"] for w in o["writes_to"]))}">'
            f'<td><strong>{_esc(o["name"])}</strong><br><span class="dim">{_esc(o["key"])}</span></td>'
            f'<td>{writes}</td><td>{holds or "<span class=dim>-</span>"}</td>'
            f'<td class="dim">{types}</td><td>{_esc(o["first_seen"] or "")} to {_esc(o["last_seen"] or "")}</td><td>{link}</td></tr>'
        )
    return "\n".join(out)


def _sections(orgs: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for o in orgs:
        groups.setdefault(o["category"], []).append(o)
    order = ["finance", "government", "utilities", "health", "telecom", "travel", "work", "social", "shopping", "other"]
    parts = []
    for cat in order:
        if cat not in groups:
            continue
        parts.append(
            f'<section><h2>{_esc(cat)} <span class="dim">({len(groups[cat])})</span></h2><div class="wrap"><table>'
            '<thead><tr><th>Organisation</th><th>Writes to</th><th>Holds</th><th>Mail</th><th>Seen</th><th>Delete</th></tr></thead>'
            f'<tbody>{_rows(groups[cat])}</tbody></table></div></section>'
        )
    return "\n".join(parts)


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    self_options = "".join(f'<option value="{_esc(s["address"])}">{_esc(s["address"])}</option>' for s in data["self"])
    src = data["source"]
    body_sections = _sections(data["organisations"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>accountscope inventory</title><style>{CSS}</style></head>
<body>
<h1>Your accounts</h1>
<p class="meta">{len(data["organisations"])} organisations from {_esc(src.get("path", ""))} · {src.get("messages", 0):,} messages · generated {_esc(data.get("generated_at", ""))}</p>
<div class="tools" id="tools" hidden>
  <input id="q" type="search" placeholder="Search organisations" aria-label="Search">
  <select id="addr" aria-label="Writes to"><option value="">any of my addresses</option>{self_options}</select>
  <button class="chip" data-filter="card" aria-pressed="false" type="button">holds card</button>
  <button class="chip" data-filter="phone" aria-pressed="false" type="button">holds phone</button>
  <button class="chip" data-filter="marketing" aria-pressed="false" type="button">newsletters only</button>
</div>
<noscript><p class="meta">Scripting is off; the full table is below.</p></noscript>
{body_sections}
<script id="inventory" type="application/json">{payload}</script>
<script>{JS}</script>
</body></html>
"""


def write_html(data: dict, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render_html(data), encoding="utf-8")
    tmp.replace(path)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_viewer.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add accountscope/viewer.py tests/test_viewer.py
git commit -m "Add self-contained HTML inventory viewer

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Change checklist

**Files:**
- Create: `accountscope/change.py`
- Test: `tests/test_change.py`

**Interfaces:**
- Consumes: `canonical` (Task 3); inventory dict shape (Task 6).
- Produces: `KINDS = ("email", "phone", "address", "card")`; `TIER1`, `TIER2` frozensets; `@dataclass Row(name, key, category, tier, last, holds: list[str], link, reason, marketing_only)`; `build_checklist(data: dict, kind: str, old: str | None, new: str | None = None) -> list[Row]`; `render_markdown(rows, kind, old, new) -> str`; `render_terminal(rows, kind, old, new) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_change.py`:
```python
import json

from accountscope.change import TIER1, Row, build_checklist, render_markdown, render_terminal
from tests.test_report import DATA


def make_data():
    data = json.loads(json.dumps(DATA))
    data["organisations"].append({
        "key": "power.example", "name": "City Power", "sender_addresses": ["bills@power.example"],
        "types": {"statement": 20}, "marketing_only": False, "first_seen": "2018-01-01", "last_seen": "2025-12-01",
        "writes_to": [{"address": "old@isp.net", "last": "2025-12-01", "count": 20}],
        "holds": [{"fact": "phone", "value": "ending 1234", "evidence": "e", "seen": "2025-11-01", "confidence": "medium", "inferred": True}],
        "delete": None, "category": "utilities", "via_relay": False})
    data["organisations"].append({
        "key": "gov.example", "name": "Tax Office", "sender_addresses": ["no-reply@gov.example"],
        "types": {"notice": 5}, "marketing_only": False, "first_seen": "2021-01-01", "last_seen": "2022-01-01",
        "writes_to": [{"address": "old@isp.net", "last": "2022-01-01", "count": 5}],
        "holds": [], "delete": None, "category": "government", "via_relay": False})
    data["organisations"][1]["writes_to"] = [{"address": "old@isp.net", "last": "2026-01-01", "count": 30}]  # newsletter
    return data


def test_email_change_selects_by_writes_to_and_orders_by_tier_then_recency():
    rows = build_checklist(make_data(), "email", "Old+news@ISP.net", "new@example.org")
    assert [r.key for r in rows] == ["gov.example", "power.example", "news.example"]
    assert rows[0].tier == 1 and rows[1].tier == 2 and rows[2].marketing_only is True
    assert rows[1].last == "2025-12-01" and rows[1].link == "https://power.example"
    assert "example.com" not in [r.key for r in rows]      # bank writes only to me@gmail.com


def test_phone_change_with_value_matches_fact_tail():
    rows = build_checklist(make_data(), "phone", "+91 98765 41234")
    assert [r.key for r in rows] == ["power.example"]
    assert rows[0].reason == "holds phone ending 1234"


def test_kind_without_value_adds_check_rows_for_sensitive_categories():
    rows = build_checklist(make_data(), "card", None)
    keys = [r.key for r in rows]
    assert keys[0] == "gov.example"                      # tier 1 check row
    assert "example.com" in keys                         # holds card
    assert "power.example" in keys                       # utilities: check
    assert next(r for r in rows if r.key == "gov.example").reason == "check: government organisations commonly hold a card"
    assert "news.example" not in keys


def test_renderers():
    rows = build_checklist(make_data(), "email", "old@isp.net", "new@example.org")
    md = render_markdown(rows, "email", "old@isp.net", "new@example.org")
    assert md.startswith("# Change email: old@isp.net -> new@example.org")
    assert "- [ ] **Tax Office**" in md and "https://gov.example" in md
    assert "newsletters (1)" in md
    term = render_terminal(rows, "email", "old@isp.net", "new@example.org")
    assert "Tax Office" in term and "2022-01-01" in term
    assert TIER1 == frozenset({"finance", "government"})
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_change.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.change'`.

- [ ] **Step 3: Implement `accountscope/change.py`**

```python
"""Turn an inventory into a prioritised checklist for an email, phone, address or card change."""
from __future__ import annotations

import re
from dataclasses import dataclass

from accountscope.identity import canonical

KINDS = ("email", "phone", "address", "card")
TIER1 = frozenset({"finance", "government"})
TIER2 = frozenset({"utilities", "health", "telecom", "travel"})
CHECK_CATEGORIES = frozenset({"finance", "government", "utilities", "health"})


@dataclass
class Row:
    name: str
    key: str
    category: str
    tier: int
    last: str | None
    holds: list[str]
    link: str
    reason: str
    marketing_only: bool


def _tier(category: str) -> int:
    if category in TIER1:
        return 1
    if category in TIER2:
        return 2
    return 3


def _link(org: dict) -> str:
    delete = org.get("delete") or {}
    return delete.get("url") or f"https://{org['key']}"


def _row(org: dict, last: str | None, reason: str) -> Row:
    return Row(name=org["name"], key=org["key"], category=org["category"], tier=_tier(org["category"]), last=last,
               holds=[f"{h['fact']} {h['value']}" for h in org["holds"]], link=_link(org), reason=reason,
               marketing_only=bool(org["marketing_only"]))


def _tail(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[-4:]


def build_checklist(data: dict, kind: str, old: str | None, new: str | None = None) -> list[Row]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    rows: list[Row] = []
    if kind == "email":
        target = canonical(old or "")
        for org in data["organisations"]:
            hit = next((w for w in org["writes_to"] if w["address"] == target), None)
            if hit:
                rows.append(_row(org, hit["last"], f"writes to {target}"))
    else:
        tail = _tail(old)
        for org in data["organisations"]:
            facts = [h for h in org["holds"] if h["fact"] == kind]
            if old:
                if kind == "address":
                    facts = [h for h in facts if old.lower() in h["value"].lower()]
                else:
                    facts = [h for h in facts if tail and h["value"].endswith(tail)]
            if facts:
                latest = max(facts, key=lambda h: h["seen"])
                rows.append(_row(org, latest["seen"], f"holds {kind} {latest['value']}"))
            elif not old and org["category"] in CHECK_CATEGORIES and not org["marketing_only"]:
                rows.append(_row(org, org["last_seen"], f"check: {org['category']} organisations commonly hold a {kind}"))
    rows.sort(key=lambda r: (r.marketing_only, r.tier, r.last is None, "" if r.last is None else r.last), reverse=False)
    # Sort recency descending within tier: re-sort with a composite key.
    rows.sort(key=lambda r: (r.marketing_only, r.tier, -(int((r.last or "0000-00-00").replace("-", "")))))
    return rows


def _split(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    return [r for r in rows if not r.marketing_only], [r for r in rows if r.marketing_only]


def render_markdown(rows: list[Row], kind: str, old: str | None, new: str | None) -> str:
    title = f"# Change {kind}: {old or 'any'}" + (f" -> {new}" if new else "")
    main, newsletters = _split(rows)
    lines = [title, ""]
    tier = None
    for r in main:
        if r.tier != tier:
            tier = r.tier
            lines.append({1: "## First: money and government", 2: "## Then: utilities, health, telecom, travel", 3: "## Everything else"}[tier])
        holds = f" · holds {', '.join(r.holds)}" if r.holds else ""
        lines.append(f"- [ ] **{r.name}** ({r.key}) · last {r.last or 'undated'} · {r.reason}{holds} · [change it here]({r.link})")
    if newsletters:
        lines.append("")
        lines.append(f"## newsletters ({len(newsletters)})")
        for r in newsletters:
            lines.append(f"- [ ] {r.name} ({r.key}) · [unsubscribe or update]({r.link})")
    return "\n".join(lines) + "\n"


def render_terminal(rows: list[Row], kind: str, old: str | None, new: str | None) -> str:
    main, newsletters = _split(rows)
    lines = [f"change {kind}: {old or 'any'}" + (f" -> {new}" if new else ""), ""]
    lines.append(f"  {'tier':<4} {'last':<11} {'organisation':<34} reason")
    for r in main:
        lines.append(f"  {r.tier:<4} {r.last or '-':<11} {r.name[:33]:<34} {r.reason}")
        lines.append(f"       {'':<11} {'':<34} {r.link}")
    if newsletters:
        lines.append(f"  newsletters ({len(newsletters)}): " + ", ".join(r.name for r in newsletters[:8]) + (" ..." if len(newsletters) > 8 else ""))
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests; simplify the double sort**

Run: `python3 -m pytest tests/test_change.py -v`
Expected: 4 passed. Then delete the first `rows.sort(...)` call (the one with `reverse=False`); the second composite sort alone is correct. Re-run to confirm 4 passed.

- [ ] **Step 5: Commit**

```bash
git add accountscope/change.py tests/test_change.py
git commit -m "Build tiered change checklists from the inventory

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: CLI with `scan` and `change`

**Files:**
- Create: `accountscope/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str] | None = None) -> int`; commands:
  - `accountscope scan MBOX [--me ADDR ...] [--not-me ADDR ...] [--out-dir DIR] [--csv] [--no-html]`
  - `accountscope change {email,phone,address,card} OLD [NEW] INVENTORY [--out FILE]`
  - `accountscope --version`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import json

from accountscope.cli import main
from tests.helpers import make_mbox

BANK = (
    "From: Example Bank <alerts@example.com>\nTo: me@gmail.com\nDelivered-To: me@gmail.com\n"
    "Date: Tue, 03 Sep 2024 10:15:00 +0000\nSubject: Your statement is ready\nContent-Type: text/plain\n\n"
    "Your Visa card ending in 4421 was charged.\n"
)
BANK_OLD = (
    "From: Example Bank <alerts@example.com>\nTo: old@isp.net\n"
    "Date: Fri, 04 Jan 2019 10:15:00 +0000\nSubject: 123456 is your OTP\nContent-Type: text/plain\n\n"
    "We sent a code to your phone number ******7788.\n"
)
NEWS = (
    "From: Deals <deals@shop.example>\nTo: me@gmail.com\nDate: Mon, 01 Jan 2024 00:00:00 +0000\n"
    "Subject: Big sale\nList-Unsubscribe: <mailto:u@shop.example>\nContent-Type: text/plain\n\nSale!\n"
)


def build(tmp_path):
    msgs = [BANK] * 3 + [BANK_OLD] + [NEWS] * 2
    return make_mbox(tmp_path, msgs)


def test_scan_writes_outputs_and_summary(tmp_path, capsys):
    path = build(tmp_path)
    code = main(["scan", str(path), "--me", "old@isp.net", "--csv"])
    out = capsys.readouterr().out
    assert code == 0
    assert "messages: 6" in out and "me@gmail.com" in out
    data = json.loads((tmp_path / "accountscope.json").read_text())
    assert data["schema"] == "accountscope/1"
    bank = next(o for o in data["organisations"] if o["key"] == "example.com")
    assert {w["address"] for w in bank["writes_to"]} == {"me@gmail.com", "old@isp.net"}
    facts = {(h["fact"], h["value"]) for h in bank["holds"]}
    assert ("card", "ending 4421") in facts and ("phone", "ending 7788") in facts
    assert (tmp_path / "accountscope.html").exists() and (tmp_path / "accountscope.csv").exists()


def test_scan_rejects_non_mbox(tmp_path, capsys):
    p = tmp_path / "x.txt"
    p.write_text("nope")
    assert main(["scan", str(p)]) == 2
    assert "mbox" in capsys.readouterr().err


def test_scan_without_recipients_explains_me_flag(tmp_path, capsys):
    path = make_mbox(tmp_path, ["From: a@b.org\nSubject: hi\n\nbody\n"])
    assert main(["scan", str(path)]) == 2
    assert "--me" in capsys.readouterr().err


def test_change_email_reads_inventory_only(tmp_path, capsys):
    path = build(tmp_path)
    assert main(["scan", str(path), "--me", "old@isp.net", "--no-html"]) == 0
    capsys.readouterr()
    out_md = tmp_path / "checklist.md"
    code = main(["change", "email", "old@isp.net", "new@example.org", str(tmp_path / "accountscope.json"), "--out", str(out_md)])
    assert code == 0
    term = capsys.readouterr().out
    assert "Example Bank" in term
    assert "- [ ] **Example Bank**" in out_md.read_text()


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as e:
        assert e.code == 0
    assert "0.1.0" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'accountscope.cli'`.

- [ ] **Step 3: Implement `accountscope/cli.py`**

```python
"""Command-line entry point: `accountscope scan` and `accountscope change`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from accountscope import __version__
from accountscope.change import KINDS, build_checklist, render_markdown, render_terminal
from accountscope.classify import classify, load_rules
from accountscope.facts import extract_facts, merge_facts
from accountscope.identity import SelfDetector
from accountscope.inventory import Aggregator
from accountscope.mbox import BodyReader, MboxStats, NotAnMbox, check_mbox, iter_messages
from accountscope.orgs import identify, load_relays
from accountscope.report import render_summary, write_csv, write_json
from accountscope.viewer import write_html


def _err(message: str) -> None:
    print(f"accountscope: {message}", file=sys.stderr)


def run_scan(args: argparse.Namespace) -> int:
    path = Path(args.mbox)
    if not path.exists():
        _err(f"{path} does not exist")
        return 2
    try:
        check_mbox(path)
    except NotAnMbox as exc:
        _err(str(exc))
        return 2

    rules = load_rules()
    relays = load_relays()
    stats = MboxStats()
    detector = SelfDetector()
    aggregator = Aggregator()
    first_day = last_day = None

    for message in iter_messages(path, stats):
        detector.add(message.recipients)
        identity = identify(message.sender, message.sender_name, message.reply_to, relays)
        msg_type = classify(message.subject, message.has_list_unsubscribe, rules)
        aggregator.add(message, identity, msg_type)
        if message.date:
            day = message.date.date().isoformat()
            first_day = day if first_day is None else min(first_day, day)
            last_day = day if last_day is None else max(last_day, day)

    if stats.total == 0:
        _err(f"{path} contains no messages")
        return 2
    self_addresses = detector.resolve(stats.total, args.me or [], args.not_me or [])
    if not self_addresses:
        _err("could not find any recipient address that looks like yours (this export may strip To/Delivered-To headers); "
             "pass your address with --me, e.g. --me you@example.com")
        return 2

    source = {"path": str(path), "messages": stats.total, "skipped": stats.skipped,
              "date_range": [first_day, last_day] if first_day else None}
    inventory = aggregator.finish(source, self_addresses)

    body_failures = 0
    reader = BodyReader(path)
    try:
        for org in inventory.organisations:
            hits = []
            for seen, key in org.pass2:
                text = reader.text(key)
                if not text:
                    body_failures += 1
                    continue
                hits.extend(extract_facts(text, seen or (org.last_seen or "")))
            org.holds = merge_facts(hits)
    finally:
        reader.close()

    out_dir = Path(args.out_dir) if args.out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    data = inventory.to_dict()
    outputs = []
    json_path = out_dir / "accountscope.json"
    write_json(data, json_path)
    outputs.append(json_path)
    if not args.no_html:
        html_path = out_dir / "accountscope.html"
        write_html(data, html_path)
        outputs.append(html_path)
    if args.csv:
        csv_path = out_dir / "accountscope.csv"
        write_csv(data, csv_path)
        outputs.append(csv_path)

    print(render_summary(data, {"skipped": stats.skipped, "no_recipients": stats.no_recipients,
                                "body_failures": body_failures}, outputs))
    return 0


def run_change(args: argparse.Namespace) -> int:
    inv_path = Path(args.inventory)
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _err(f"cannot read inventory {inv_path}: {exc}")
        return 2
    schema = str(data.get("schema", ""))
    if not schema.startswith("accountscope/1"):
        _err(f"unsupported inventory schema {schema!r}; expected accountscope/1")
        return 2
    rows = build_checklist(data, args.kind, args.old, args.new)
    print(render_terminal(rows, args.kind, args.old, args.new))
    if args.out:
        Path(args.out).write_text(render_markdown(rows, args.kind, args.old, args.new), encoding="utf-8")
        print(f"\nwritten: {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="accountscope",
                                     description="Inventory the organisations that hold an account for you, from a mailbox export. Zero network.")
    parser.add_argument("--version", action="version", version=f"accountscope {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="build the inventory from an mbox file")
    scan.add_argument("mbox", help="path to an mbox file (Google Takeout, Thunderbird)")
    scan.add_argument("--me", action="append", metavar="ADDR", help="an address that is yours (repeatable)")
    scan.add_argument("--not-me", action="append", metavar="ADDR", help="an address to exclude (repeatable)")
    scan.add_argument("--out-dir", metavar="DIR", help="where to write outputs (default: next to the mbox)")
    scan.add_argument("--csv", action="store_true", help="also write accountscope.csv")
    scan.add_argument("--no-html", action="store_true", help="skip the HTML viewer")
    scan.set_defaults(func=run_scan)

    change = sub.add_parser("change", help="list the organisations to update after a change")
    change.add_argument("kind", choices=KINDS)
    change.add_argument("old", nargs="?", default=None, help="the old value (email address, phone, address fragment, card tail)")
    change.add_argument("new", nargs="?", default=None, help="the new value, for the checklist title")
    change.add_argument("inventory", help="path to accountscope.json")
    change.set_defaults(func=run_change)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _err("interrupted")
        return 1
    except Exception as exc:  # noqa: BLE001 - last-resort reporting
        _err(f"unexpected error: {exc}")
        return 1
```

Note on `change` positional parsing: with `old` and `new` optional and `inventory` required, argparse assigns `change email old.json` as `old="old.json"`... To avoid ambiguity, require `--inventory`? No: the tests call `change email old new inventory.json`. argparse fills positionals greedily left to right: for 4 tokens → old, new, inventory; for 3 → old, inventory (new=None); for 2 → inventory only. This is what we want. Add `--out FILE` to the `change` parser: `change.add_argument("--out", metavar="FILE", help="also write a Markdown checklist")`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: 5 passed. If `test_version` fails because argparse writes the version to stdout only in Python ≥ 3.4 (it does), check the captured `out`.

- [ ] **Step 5: Run the full suite and the real entry point**

Run: `python3 -m pytest -q && accountscope --version`
Expected: all tests pass; `accountscope 0.1.0`.

- [ ] **Step 6: Commit**

```bash
git add accountscope/cli.py tests/test_cli.py
git commit -m "Add scan and change commands

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Labelled precision gate, docs, README

**Files:**
- Create: `tests/labelled/messages.jsonl`, `tests/test_precision.py`, `docs/precision.md`
- Modify: `README.md`, `CHANGELOG.md`

**Interfaces:**
- `tests/labelled/messages.jsonl`: one JSON object per line: `{"subject": str, "list_unsubscribe": bool, "body": str, "type": str, "facts": [{"fact": str, "value": str}]}`.

- [ ] **Step 1: Write the labelled seed set**

`tests/labelled/messages.jsonl` — start with these 16 lines, then grow the file to at least 300 lines before release by copying real-shaped messages from your own mailbox with names, numbers and addresses replaced (keep the structure, change the identifiers):
```
{"subject": "Your verification code is 483920", "list_unsubscribe": false, "body": "Use code 483920 to sign in. It expires in 10 minutes.", "type": "otp", "facts": []}
{"subject": "Verify your email address", "list_unsubscribe": false, "body": "Click the link to verify your email.", "type": "verify", "facts": []}
{"subject": "Reset your password", "list_unsubscribe": false, "body": "We received a request to reset your password.", "type": "reset", "facts": []}
{"subject": "Welcome to Example!", "list_unsubscribe": false, "body": "Thanks for signing up. Get started here.", "type": "signup", "facts": []}
{"subject": "Your receipt from Example Store", "list_unsubscribe": false, "body": "Paid with card ending 4421. Total $12.00.", "type": "receipt", "facts": [{"fact": "card", "value": "ending 4421"}]}
{"subject": "Order #4521 confirmed", "list_unsubscribe": false, "body": "Shipping address:\nA Person\n12 High St\nLondon SW1A 1AA", "type": "receipt", "facts": [{"fact": "address", "value": "London SW1A 1AA"}]}
{"subject": "Your statement is ready", "list_unsubscribe": false, "body": "Your September statement is available online.", "type": "statement", "facts": []}
{"subject": "Your order has shipped", "list_unsubscribe": false, "body": "Delivery address:\nA Person\n221B Baker Street\nLondon NW1 6XE", "type": "notice", "facts": [{"fact": "address", "value": "London NW1 6XE"}]}
{"subject": "Autopay reminder", "list_unsubscribe": false, "body": "Your autopay of $40 is scheduled from the card ending in 9876.", "type": "notice", "facts": [{"fact": "card", "value": "ending 9876"}]}
{"subject": "123456 is your OTP", "list_unsubscribe": false, "body": "We sent a code to your phone number ******1234.", "type": "otp", "facts": [{"fact": "phone", "value": "ending 1234"}]}
{"subject": "Big spring sale!", "list_unsubscribe": true, "body": "Get 20% off with code SAVE20 on orders over $50.", "type": "marketing", "facts": []}
{"subject": "Weekly digest", "list_unsubscribe": true, "body": "Top stories this week.", "type": "marketing", "facts": []}
{"subject": "Su código es 998877", "list_unsubscribe": false, "body": "Su código de verificación es 998877.", "type": "otp", "facts": []}
{"subject": "Bem-vindo à Loja", "list_unsubscribe": false, "body": "Obrigado por se registar.", "type": "signup", "facts": []}
{"subject": "Ihre Rechnung", "list_unsubscribe": false, "body": "Vielen Dank für Ihre Bestellung.", "type": "receipt", "facts": []}
{"subject": "Re: lunch tomorrow?", "list_unsubscribe": false, "body": "Sure, 1pm works. See you at the usual place.", "type": "other", "facts": []}
```

- [ ] **Step 2: Write the precision test**

`tests/test_precision.py`:
```python
import json
from pathlib import Path

from accountscope.classify import classify
from accountscope.facts import extract_facts

LABELLED = Path(__file__).parent / "labelled" / "messages.jsonl"
THRESHOLD = 0.70


def load():
    return [json.loads(line) for line in LABELLED.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_type_precision_meets_threshold():
    rows = load()
    correct = sum(1 for r in rows if classify(r["subject"], r["list_unsubscribe"]) == r["type"])
    precision = correct / len(rows)
    print(f"\ntype precision: {precision:.2%} ({correct}/{len(rows)})")
    assert precision >= THRESHOLD


def test_fact_precision_meets_threshold():
    rows = load()
    predicted = 0
    correct = 0
    expected_total = 0
    found = 0
    for r in rows:
        expected = {(f["fact"], f["value"]) for f in r["facts"]}
        expected_total += len(expected)
        got = {(h.fact, h.value) for h in extract_facts(r["body"], "2024-01-01")}
        predicted += len(got)
        correct += len(got & expected)
        found += len(got & expected)
    precision = correct / predicted if predicted else 1.0
    recall = found / expected_total if expected_total else 1.0
    print(f"\nfact precision: {precision:.2%} ({correct}/{predicted}); recall: {recall:.2%} ({found}/{expected_total})")
    assert precision >= THRESHOLD
```

- [ ] **Step 3: Run the precision tests**

Run: `python3 -m pytest tests/test_precision.py -v -s`
Expected: 2 passed, with printed precision at 100% on the seed set. (The gate becomes meaningful once the set grows.)

- [ ] **Step 4: Write `docs/precision.md`**

```markdown
# Measuring precision on a real mailbox

accountscope's held-fact and message-type heuristics are only as good as their
precision on real mail. Before each release, run the tool on one real, ten-year
mailbox and record the numbers below. Nothing from the mailbox is committed.

1. Export the mailbox: Google Takeout → Mail → "All mail" as mbox, or in
   Thunderbird right-click the folder → Export (ImportExportTools NG) → mbox.
2. Run `accountscope scan path/to/mail.mbox --out-dir /tmp/scope`.
3. Open `/tmp/scope/accountscope.html`. Sample 100 organisations at random
   (`python3 -c "import json,random;d=json.load(open('/tmp/scope/accountscope.json'));[print(o['key']) for o in random.sample(d['organisations'],100)]"`).
4. For each sampled organisation, judge: is the organisation real and correctly
   named (yes/no); is each `holds` fact true (yes/no, checking the evidence
   snippet against the original mail); is `writes_to` correct.
5. Record: organisation precision = correct / 100; fact precision = true facts /
   all sampled facts. Copy both into the README table with the date and the
   accountscope version.

If fact precision for a fact type is below 70%, set `"inferred": true` facts of
that type to be excluded from the change checklist (see `change.py`,
`CHECK_CATEGORIES`) and open an issue with the failing snippets (identifiers
replaced).
```

- [ ] **Step 5: Write the README**

Replace `README.md` with:
```markdown
# accountscope

You have no list of which websites and companies you have signed up with over the
years, or which email address, phone number, home address or card each one is
using. So every time one of those changes, or a relative dies, you spend weeks
hunting through your inbox to find them all.

accountscope reads a mailbox export and builds that list. It never touches the
network.

```
$ accountscope scan takeout.mbox

messages: 184,211   skipped: 37 malformed, 0 without recipients, 12 bodies unreadable
dates:    2014-03-02 to 2026-09-30

your addresses (inferred from recipient headers; fix with --me / --not-me):
  me@gmail.com                              181,004 messages  aliases: me+shop@gmail.com
  old@isp.net                                 3,110 messages

organisations: 612   (388 newsletters only)
  shopping: 201   other: 190   finance: 84   work: 52   travel: 31   social: 22   utilities: 14   health: 11   government: 7

most active accounts (transactional mail)
  messages  last seen   holds                  organisation
       150  2026-09-28  card                   Example Bank (example.com)
        96  2026-09-12  address, card          Example Store (store.example)
  ...

written:
  /Users/you/takeout/accountscope.json
  /Users/you/takeout/accountscope.html
```

## What it records that nothing else does

For every organisation, **which of your own addresses it writes to** and when it
last did, read from the To, Cc, Delivered-To, X-Original-To and Envelope-To
headers. That is what turns the inventory into a migration list:

```
$ accountscope change email old@isp.net new@example.org accountscope.json --out checklist.md

change email: old@isp.net -> new@example.org

  tier last        organisation                       reason
  1    2025-12-01  Tax Office                         writes to old@isp.net
                                                      https://gov.example
  2    2025-12-01  City Power                         writes to old@isp.net
  ...
```

Also recorded, conservatively and with the evidence snippet: whether the
organisation holds a card (as "ending 4421"), a phone number (masked tail), or a
postal address (town and postcode line). Full numbers are never reconstructed.

## Privacy

accountscope opens no network connection. The public-suffix list and the
[JustDeleteMe](https://justdeleteme.xyz) data it uses are bundled at release
time. The test suite makes `socket.socket` raise, so any change that opens a
connection fails the tests (`tests/conftest.py`). The JSON it writes contains
no message bodies, no subjects and no third-party addresses.

## Getting your mbox

- **Gmail**: [Google Takeout](https://takeout.google.com) → deselect all →
  select Mail → "All mail data included" → export. You get one `.mbox` file
  (often many GB; that is fine, accountscope streams it).
- **Thunderbird**: install ImportExportTools NG, right-click a folder → Export
  folder → mbox. Thunderbird can also pull an IMAP account down first, which is
  the route for Outlook.com, Yahoo and most ISP mailboxes.

## Install

```
pip install accountscope
```

Python 3.10 or newer. No dependencies.

## Precision

| Date | Version | Organisations correct | Held facts correct | Sample |
|---|---|---|---|---|
| (run docs/precision.md before the first release) | 0.1.0 | – | – | 100 orgs of one 10-year mailbox |

## Not in v1

IMAP, Apple Mail `.emlx` folders, Outlook `.pst`, password-manager import, the
"if I'm gone" family export, a GUI, and anything that logs in or changes an
account for you. The tool produces the list and the links.

## Licence

MIT
```

- [ ] **Step 6: Update the CHANGELOG**

```markdown
# Changelog

## 0.1.0 (unreleased)
- `accountscope scan`: inventory from an mbox with self-address inference,
  organisation identity via the public-suffix list, message typing, `writes_to`
  per organisation, conservative held-fact extraction, JSON/HTML/CSV output.
- `accountscope change`: tiered checklist for an email, phone, address or card change.
- Zero-network guarantee enforced by the test suite.
```

- [ ] **Step 7: Run everything and commit**

Run: `python3 -m pytest -q`
Expected: all passed.

```bash
git add -A
git commit -m "Add precision gate, README and docs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review against the spec

- **Spec coverage.** §1 goal and success criteria → Tasks 2-12; §2 scope (mbox only, outputs, translations) → Tasks 2, 5, 8, 9, 10; §3 architecture (two passes, pass-2 cap, module table) → Tasks 2, 6, 7, 11, with the viewer split noted; §4 schema → Task 6 `to_dict` and Task 8/9 consumers, schema check in `run_change`; §5 rules (self threshold, relays, ordered types, translations, fact regexes, confidence) → Tasks 3, 4, 5, 7; §6 checklist (selection, tiers, check rows, links, Markdown) → Task 10; §7 outputs (terminal, atomic JSON, HTML with noscript, CSV, Markdown) → Tasks 8, 9, 10, 11; §8 privacy and errors (no network imports, socket guard, exit codes, skip counts) → Tasks 1, 2, 11; §9 testing (per-module tests, fixtures via `make_mbox`, labelled set, precision gate, manual run) → every task plus Task 12; §10 repository layout and release → Tasks 1, 4, 12; §11 kill conditions → carried in the spec, not code.
- **Gap noted.** The spec's "exclude a fact type from the checklist if precision < 70%" is a manual release decision documented in `docs/precision.md`, not an automatic switch; `Fact.inferred` is written so a later version can flip it per type.
- **Placeholder scan.** No TBD/TODO. The labelled set is a real 16-line seed with an explicit growth instruction, not a placeholder.
- **Type consistency.** `Message` fields (Task 2) are used identically in Tasks 6 and 11; `SelfAddress.to_dict()` (Task 3) is consumed by `Inventory.to_dict()` (Task 6) and asserted in Task 6's test; `OrgIdentity(key, name, via_relay)` (Task 4) matches `Aggregator.add` (Task 6) and `run_scan` (Task 11); `Fact` (Task 6) is produced by `merge_facts` (Task 7) and serialised with `inferred`; `render_summary(data, stats_extra, outputs)` (Task 8) is called with those three arguments in Task 11; `build_checklist(data, kind, old, new)` (Task 10) matches `run_change` (Task 11); `KINDS` is imported in Task 11 from Task 10.
