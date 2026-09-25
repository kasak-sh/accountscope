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
