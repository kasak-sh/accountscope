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
