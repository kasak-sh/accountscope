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
