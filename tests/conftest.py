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
