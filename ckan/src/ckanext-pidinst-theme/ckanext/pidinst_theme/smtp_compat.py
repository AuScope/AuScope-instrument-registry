"""Compatibility shim for CKAN's SMTP configuration.

CKAN has no ``smtp.port`` option: ``ckan/lib/mailer.py`` passes
``config['smtp.server']`` straight to ``smtplib.SMTP()`` as one argument, so a
non-default port can only be given as ``"host:port"`` -- which is what CKAN's
own config example (``smtp.example.com:587``) recommends.

``smtplib.SMTP.__init__`` stores that raw string in ``self._host`` *before*
``connect()`` splits the port off it.  ``starttls()`` later passes
``self._host`` verbatim as the TLS SNI server name, so the server is sent
``"email-smtp.ap-southeast-2.amazonaws.com:587"`` -- not a valid hostname.
Amazon SES aborts the handshake with::

    ssl.SSLError: [SSL: SSLV3_ALERT_ILLEGAL_PARAMETER] sslv3 alert illegal parameter

surfacing in the UI as "Server not connected".

This shim splits the port off before delegating, so SNI is a bare hostname.
We must keep port 587 (AWS restricts outbound TCP 25 from EC2), so dropping the
``:587`` suffix from the config is not an option.
"""

import functools
import logging
import smtplib

log = logging.getLogger(__name__)

_PATCH_MARKER = "_pidinst_hostport_split"


def install():
    """Idempotently patch ``smtplib.SMTP.__init__`` to split ``host:port``."""
    original = smtplib.SMTP.__init__
    if getattr(original, _PATCH_MARKER, False):
        return

    @functools.wraps(original)
    def __init__(self, host="", port=0, *args, **kwargs):
        # Only act on an unambiguous "host:port" with no explicit port argument.
        # A bracketed IPv6 literal or a bare IPv6 address has != 1 colon and is
        # left untouched.
        if host and not port and host.count(":") == 1:
            candidate_host, _, candidate_port = host.partition(":")
            try:
                port = int(candidate_port)
            except ValueError:
                pass  # not a port; hand the original string through unchanged
            else:
                host = candidate_host
        return original(self, host, port, *args, **kwargs)

    setattr(__init__, _PATCH_MARKER, True)
    smtplib.SMTP.__init__ = __init__


try:
    install()
except Exception as e:  # pragma: no cover - defensive, keeps plugin importable
    log.error(f"Failed to install the smtplib host:port compatibility shim: {e}")
