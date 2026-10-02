"""Offline safety guard for the Python suite; injected fake sessions still work."""

import socket

import pytest
import requests


@pytest.fixture(autouse=True)
def deny_unmocked_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unmocked outbound request blocked by the offline test suite.")

    monkeypatch.setattr(requests.sessions.Session, "request", denied)
    # Standard-library workflow helpers use urllib rather than Requests.
    # Block actual sockets too, while allowing explicitly injected HTTP doubles.
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
