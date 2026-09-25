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
