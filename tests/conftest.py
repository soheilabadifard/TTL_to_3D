import base64
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


@pytest.fixture
def tiny_trix():
    return FIXTURES / "tiny.trix"


@pytest.fixture
def xml_bomb():
    """RDF/XML whose one literal is an entity expanding to 3 GB."""
    return BOMB


@pytest.fixture
def xml_peek():
    """RDF/XML whose one literal is an external entity naming tests/fixtures/library.ttl."""
    return PEEK


@pytest.fixture(autouse=True)
def _clean_sparql_env(monkeypatch):
    """No test should see a real credential from the developer's shell, and a local HTTP(S) proxy
    must never intercept a loopback request meant for the stub endpoint."""
    for name in ("TTL3D_SPARQL_USER", "TTL3D_SPARQL_PASSWORD", "TTL3D_SPARQL_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


TURTLE = (b"@prefix ex: <http://example.org/q#> .\n"
          b"ex:a ex:p ex:b .\nex:a <http://www.w3.org/2000/01/rdf-schema#label> \"A\" .\n")
NT = b"<http://example.org/q#a> <http://example.org/q#p> <http://example.org/q#b> .\n"
JSONLD = b'[{"@id": "http://example.org/q#a", "http://example.org/q#p": [{"@id": "http://example.org/q#b"}]}]'
TRIG = (b"@prefix ex: <http://example.org/q#> .\n"
        b"ex:g1 { ex:a ex:p ex:b . }\nex:g2 { ex:c ex:p ex:d . }\n")
RELATIVE = b"<rel/a> <http://example.org/q#p> <rel/b> .\n"
_RDF_XML = ('<?xml version="1.0"?>\n<!DOCTYPE rdf:RDF [{}]>\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:ex="http://example.org/x#">'
            '<rdf:Description rdf:about="http://example.org/x#a"><ex:p>{}</ex:p></rdf:Description></rdf:RDF>\n')
# ten entities, each ten of the one before: "lol" expands to 3 GB ("billion laughs")
BOMB = _RDF_XML.format('<!ENTITY l0 "lol">' + "".join(f'<!ENTITY l{i} "{f"&l{i - 1};" * 10}">'
                                                      for i in range(1, 10)), "&l9;").encode()
# an external entity naming a local file: a parser that fetched it would put the file's text in the data
PEEK = _RDF_XML.format(f'<!ENTITY peek SYSTEM "{(FIXTURES / "library.ttl").as_uri()}">', "&peek;").encode()
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
    "/moved307": (307, None, b""),                      # same Location as /moved, a 307 instead
    "/movedecho": (302, None, b""),                     # echoes the credential into the Location path
    "/nolength": (200, "text/turtle", TURTLE),          # no Content-Length: the body ends when it closes
    "/slow500": (500, "text/plain", b"too late"),       # the error body comes 1.5 s after the headers
    "/bomb": (200, "application/rdf+xml", BOMB),
    "/peek": (200, "application/rdf+xml", PEEK),
}


class _StubEndpoint(BaseHTTPRequestHandler):
    """A SPARQL endpoint that answers by path (ANSWERS): /auth wants an Authorization header, /slow
    sleeps first, /moved and /moved307 redirect with user info and a signed query string in their
    Location, /movedecho redirects to a path holding the Authorization header's credential, /echo puts
    that header in its error body (and, for a Basic header, the decoded user:password too), /nolength
    sends no Content-Length, /slow500 sleeps between its headers and its body, /chunkcut sends one
    complete chunk of a chunked answer and closes before the terminating chunk. Every request is
    recorded on the server as (path, headers, body)."""

    def log_message(self, *args):             # keep pytest's output clean
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.server.requests.append((self.path, dict(self.headers), body))
        if self.path == "/chunkcut":
            self.send_response(200)
            self.send_header("Content-Type", "text/turtle")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"5\r\n@pref\r\n")   # one full chunk promised and sent, then it just closes
            return
        status, media, data = ANSWERS.get(self.path, (404, "text/plain", b"no such path"))
        if self.path == "/auth" and "Authorization" not in self.headers:
            status, data = 401, b""
        if self.path == "/echo":
            auth = self.headers.get("Authorization", "")
            data = ("echo: " + auth).encode()
            if auth.startswith("Basic "):
                data += (" = " + base64.b64decode(auth[len("Basic "):]).decode()).encode()
        if self.path == "/slow":
            time.sleep(1.5)
        self.send_response(status)
        port = self.server.server_address[1]
        if self.path in ("/moved", "/moved307"):
            self.send_header("Location", f"http://alice:hunter2@127.0.0.1:{port}/sparql?key=SIGNED#f")
        if self.path == "/movedecho":
            credential = self.headers.get("Authorization", "none").split(" ", 1)[-1]
            self.send_header("Location", f"http://127.0.0.1:{port}/{credential}/sparql")
        if media:
            self.send_header("Content-Type", media + ("; charset=utf-8" if media.startswith("text/") else ""))
        if self.path != "/nolength":
            self.send_header("Content-Length", "100" if self.path == "/cut" else str(len(data)))
        self.end_headers()
        if self.path == "/slow500":
            time.sleep(1.5)
        self.wfile.write(data)


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # a client that gave up (the timeout test) is not noise; anything else is a stub bug: show it
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


@pytest.fixture
def endpoint():
    """A stub SPARQL endpoint on the loopback address: `.url` is its base, `.where` its host and port as
    messages name it, `.requests` what it saw."""
    server = _QuietServer(("127.0.0.1", 0), _StubEndpoint)
    server.requests = []
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    server.where = server.url[len("http://"):]       # how messages name it: host and port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
