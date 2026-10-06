"""Polite HTTP fetching for TCB's website and its file storage.

Rules: at least MIN_DELAY seconds between requests to the same host (plus jitter),
exponential back-off on 429/5xx, and no attempt to look like a browser. TLS
verification is skipped only for a host that fails a real handshake (tcb.gov.bd
serves an incomplete certificate chain), never by a blanket setting.
"""
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "BazarPulse/0.1 (+https://github.com/Sakib9797/Bazar-Pulse)"
MIN_DELAY = 6.0
JITTER = 1.5
TIMEOUT = 60
MAX_RETRIES = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}

_last_hit = {}
_tls_ok = {}


def to_uri(url):
    """Percent-encode non-ASCII paths (the CMS uses Bengali slugs)."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        p.scheme, p.netloc,
        urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;=~-._"),
        urllib.parse.quote(p.query, safe="=&%:/?@!$'()*+,;~-._"),
        p.fragment))


def _wait_turn(host):
    last = _last_hit.get(host)
    if last is not None:
        wait = MIN_DELAY + random.uniform(0, JITTER) - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.monotonic()


def tls_verifies(host):
    if host not in _tls_ok:
        try:
            with socket.create_connection((host, 443), timeout=20) as sock:
                with ssl.create_default_context().wrap_socket(sock, server_hostname=host):
                    pass
            _tls_ok[host] = True
        except ssl.SSLError:
            _tls_ok[host] = False
        except OSError:
            _tls_ok[host] = True      # not a certificate problem; let the request report it
    return _tls_ok[host]


def get(url):
    """Return the response body as bytes, retrying politely on transient failures."""
    url = to_uri(url)
    host = urllib.parse.urlsplit(url).hostname
    ctx = ssl.create_default_context()
    if not tls_verifies(host):
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(MAX_RETRIES + 1):
        _wait_turn(host)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUSES or attempt == MAX_RETRIES:
                raise
            retry_after = e.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else 20 * 2 ** attempt
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == MAX_RETRIES:
                raise
            delay = 20 * 2 ** attempt
        time.sleep(min(delay, 180))
