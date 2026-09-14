import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def library():
    return FIXTURES / "library.ttl"


@pytest.fixture
def library_extra():
    return FIXTURES / "library-extra.ttl"


@pytest.fixture
def tiny_nt():
    return FIXTURES / "tiny.nt"


@pytest.fixture
def library_trig():
    return FIXTURES / "library.trig"


@pytest.fixture
def tiny_nq():
    return FIXTURES / "tiny.nq"


TURTLE = (b"@prefix ex: <http://example.org/q#> .\n"
          b"ex:a ex:p ex:b .\nex:a <http://www.w3.org/2000/01/rdf-schema#label> \"A\" .\n")
NT = b"<http://example.org/q#a> <http://example.org/q#p> <http://example.org/q#b> .\n"
JSONLD = b'[{"@id": "http://example.org/q#a", "http://example.org/q#p": [{"@id": "http://example.org/q#b"}]}]'
TRIG = (b"@prefix ex: <http://example.org/q#> .\n"
        b"ex:g1 { ex:a ex:p ex:b . }\nex:g2 { ex:c ex:p ex:d . }\n")
RELATIVE = b"<rel/a> <http://example.org/q#p> <rel/b> .\n"
ANSWERS = {                                   # path -> (status, media type or None, body)
    "/sparql": (200, "text/turtle", TURTLE),
    "/nt": (200, "application/n-triples", NT),
    "/jsonld": (200, "application/ld+json", JSONLD),
    "/trig": (200, "application/trig", TRIG),
    "/relative": (200, "text/turtle", RELATIVE),
    "/html": (200, "text/html", b"<html>nope</html>"),
    "/notype": (200, None, TURTLE),
    "/empty": (200, "text/turtle", b""),
    "/big": (200, "text/turtle", TURTLE + b"#" * 5000 + b"\n"),
    "/cut": (200, "text/turtle", TURTLE[:10]),          # promises 100 bytes, sends 10, hangs up
    "/500": (500, "text/plain", b"Virtuoso 37000 Error SP030: SPARQL compiler\nline 2: syntax error"),
    "/echo": (500, "text/plain", b""),                  # echoes the request's Authorization header
    "/slow": (200, "text/turtle", TURTLE),
    "/auth": (200, "text/turtle", TURTLE),
    "/moved": (301, None, b""),
}


class _StubEndpoint(BaseHTTPRequestHandler):
    """A SPARQL endpoint that answers by path (ANSWERS): /auth wants an Authorization header, /slow
    sleeps first, /moved redirects with user info and a signed query string in its Location, /echo
    puts the request's Authorization header in its error body. Every request is recorded on the
    server as (path, headers, body)."""

    def log_message(self, *args):             # keep pytest's output clean
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.server.requests.append((self.path, dict(self.headers), body))
        status, media, data = ANSWERS.get(self.path, (404, "text/plain", b"no such path"))
        if self.path == "/auth" and "Authorization" not in self.headers:
            status, data = 401, b""
        if self.path == "/echo":
            data = ("echo: " + self.headers.get("Authorization", "")).encode()
        if self.path == "/slow":
            time.sleep(1.5)
        self.send_response(status)
        if self.path == "/moved":
            port = self.server.server_address[1]
            self.send_header("Location", f"http://alice:hunter2@127.0.0.1:{port}/sparql?key=SIGNED#f")
        if media:
            self.send_header("Content-Type", media + ("; charset=utf-8" if media.startswith("text/") else ""))
        self.send_header("Content-Length", "100" if self.path == "/cut" else str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # a client that gave up (the timeout test) is not noise; anything else is a stub bug: show it
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


@pytest.fixture
def endpoint():
    """A stub SPARQL endpoint on the loopback address: `.url` is its base, `.requests` what it saw."""
    server = _QuietServer(("127.0.0.1", 0), _StubEndpoint)
    server.requests = []
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
