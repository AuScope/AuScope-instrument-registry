"""Tests for smtp_compat.py."""

import smtplib

import pytest

from ckanext.pidinst_theme import smtp_compat


@pytest.fixture
def connect_calls(monkeypatch):
    """Stub SMTP.connect so no socket is opened, recording its arguments."""
    calls = []

    def fake_connect(self, host="localhost", port=0, source_address=None):
        calls.append((host, port))
        return (220, b"stub ready")

    monkeypatch.setattr(smtplib.SMTP, "connect", fake_connect)
    return calls


def _smtp(*args, **kwargs):
    # An explicit local_hostname keeps __init__ from doing an FQDN lookup.
    kwargs.setdefault("local_hostname", "test.example.com")
    return smtplib.SMTP(*args, **kwargs)


def test_host_port_string_is_split(connect_calls):
    conn = _smtp("smtp.example.com:587")

    assert connect_calls == [("smtp.example.com", 587)]
    # _host is what starttls() passes as the TLS SNI server name -- it must be
    # a bare hostname.  This is the regression being guarded.
    assert conn._host == "smtp.example.com"


def test_host_without_port_is_untouched(connect_calls):
    conn = _smtp("smtp.example.com")

    assert connect_calls == [("smtp.example.com", 0)]
    assert conn._host == "smtp.example.com"


def test_explicit_port_argument_wins(connect_calls):
    conn = _smtp("smtp.example.com", 2525)

    assert connect_calls == [("smtp.example.com", 2525)]
    assert conn._host == "smtp.example.com"


def test_non_numeric_port_is_left_alone(connect_calls):
    conn = _smtp("smtp.example.com:notaport")

    assert connect_calls == [("smtp.example.com:notaport", 0)]
    assert conn._host == "smtp.example.com:notaport"


@pytest.mark.parametrize("host", ["::1", "[::1]:587"])
def test_ipv6_hosts_are_left_alone(connect_calls, host):
    conn = _smtp(host)

    assert connect_calls == [(host, 0)]
    assert conn._host == host


def test_install_is_idempotent(connect_calls):
    smtp_compat.install()
    patched = smtplib.SMTP.__init__
    smtp_compat.install()

    assert smtplib.SMTP.__init__ is patched
    assert getattr(patched, smtp_compat._PATCH_MARKER, False) is True

    conn = _smtp("smtp.example.com:587")
    assert connect_calls == [("smtp.example.com", 587)]
    assert conn._host == "smtp.example.com"
