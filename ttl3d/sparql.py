"""Fetch a CONSTRUCT or DESCRIBE result from a SPARQL endpoint so it can be a source like a file.

    Query(endpoint, query, auth, token, timeout, max_bytes)       checked when built (__post_init__)
        --fetch: one POST--> (body of at most max_bytes, media type)
        --load.parse_data(base=endpoint)--> rdflib Dataset, folded into one legend key by load.load

A redirect is refused with the URL to use; an answer that is not Turtle, N-Triples, RDF/XML or a quad
format is refused by its media type (JSON-LD too: its parser fetches remote contexts); server text
quoted in an error has the credentials blanked. Nothing here reaches the page: a result is fetched
at build time, and the page stays self-contained.
"""
from __future__ import annotations

import base64
import http.client
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# no JSON-LD: rdflib's JSON-LD parser fetches a remote @context itself, outside fetch's rules
RDF_MEDIA_TYPES = frozenset({
    "text/turtle", "application/n-triples", "application/rdf+xml",
    "application/n-quads", "application/trig", "text/n3", "application/trix",
})
ACCEPT = "text/turtle, application/n-triples;q=0.9, application/rdf+xml;q=0.8"
USER_AGENT = "ttl3d/{} (+https://github.com/soheilabadifard/TTL_to_3D)"   # Wikidata refuses Python-urllib
MAX_BYTES = 100_000_000                  # 100 MB of answer; the parse needs about 35 times that in memory
NOT_A_GRAPH = frozenset({                # query forms and updates whose answer is not an RDF graph
    "SELECT", "ASK", "INSERT", "DELETE", "LOAD", "CLEAR", "CREATE", "DROP", "COPY", "MOVE", "ADD", "WITH",
})
_GAP = re.compile(r"(?:\s+|#[^\n]*)+")                           # whitespace and comments between tokens
_BASE = re.compile(r"BASE\s*<([^>]*)>", re.IGNORECASE)
_PREFIX = re.compile(r"PREFIX\s+([^\W\d_][\w.-]*)?:\s*<([^>]*)>", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z]+")


class FetchError(ValueError):
    """The endpoint could not be reached, refused the query, or answered something that is not RDF."""


def check_timeout(timeout) -> None:
    """A timeout is a positive, finite number of seconds (socket.settimeout overflows on inf); the CLI
    and Query share this check."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (
            timeout > 0 and math.isfinite(timeout)):
        raise ValueError(f"timeout must be a positive number of seconds, got {timeout!r}")


def _prologue(query: str) -> tuple[dict[str, str], str]:
    """Read the prologue as SPARQL does: BASE and PREFIX declarations in order, whitespace and
    comments between them skipped, each prefix IRI resolved against the latest BASE. Returns the
    prefixes (the first declaration of a prefix wins) and the first word after the prologue,
    upper-cased: "" when nothing follows, the next character when it is not a word."""
    base, prefixes, pos = "", {}, 0
    while True:
        gap = _GAP.match(query, pos)
        if gap:
            pos = gap.end()
        if (m := _BASE.match(query, pos)):
            base = urllib.parse.urljoin(base, m.group(1))
        elif (m := _PREFIX.match(query, pos)):
            prefixes.setdefault(m.group(1) or "", urllib.parse.urljoin(base, m.group(2)))
        else:
            word = _WORD.match(query, pos)
            return prefixes, word.group(0).upper() if word else query[pos:pos + 1]
        pos = m.end()


def form(query: str) -> str:
    """The query's first word after the prologue. SELECT, ASK and SPARQL Update are refused before any
    request; CONSTRUCT and DESCRIBE pass, and so does an unknown word (a store's own pragma such as
    Virtuoso's DEFINE): the endpoint judges it, and an answer that is not RDF is refused by its type."""
    keyword = _prologue(query)[1]
    if not keyword:
        raise ValueError("the query is empty")
    if keyword in NOT_A_GRAPH:
        raise ValueError(f"the query must be CONSTRUCT or DESCRIBE, not {keyword}")
    return keyword


def prefixes_in(query: str) -> dict[str, str]:
    """The prologue's PREFIX declarations as prefix -> namespace, resolved against BASE."""
    return _prologue(query)[0]


def host(endpoint: str) -> str:
    """The endpoint's hostname, for source names and messages; the endpoint itself when it has none."""
    return urllib.parse.urlsplit(endpoint).hostname or endpoint


def _where(url: str) -> str:
    """Host and path, for messages: never user info, a query string or a fragment."""
    parts = urllib.parse.urlsplit(url)
    return (parts.hostname or "") + parts.path


def _clean(url: str) -> str:
    """A server-sent URL for a message: scheme, host, port and path only."""
    parts = urllib.parse.urlsplit(url)
    try:
        port = f":{parts.port}" if parts.port else ""
    except ValueError:                                         # a malformed port in the server's URL
        port = ""
    return urllib.parse.urlunsplit((parts.scheme, (parts.hostname or "") + port, parts.path, "", ""))


@dataclass(frozen=True)
class Query:
    """A SPARQL source: one query against one endpoint. Checked when built, so an invalid Query never
    exists and nothing is sent before every query of a run is sound. `auth` is an HTTP Basic (user,
    password) pair, `token` a Bearer token, one or the other, neither shown by repr; `timeout` bounds
    each network step (connect, read) in seconds; an answer over `max_bytes` is refused."""
    endpoint: str
    query: str
    auth: tuple[str, str] | None = field(default=None, repr=False)    # never in a traceback or a notebook
    token: str | None = field(default=None, repr=False)
    timeout: float = 60.0
    max_bytes: int = MAX_BYTES

    def __post_init__(self):
        parts = urllib.parse.urlsplit(self.endpoint)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("the endpoint must be an http:// or https:// URL with a host name")
        if parts.username is not None or parts.password is not None:
            raise ValueError("the endpoint URL must not carry credentials; use TTL3D_SPARQL_USER and "
                             "TTL3D_SPARQL_PASSWORD or TTL3D_SPARQL_TOKEN (auth= or token= in Python)")
        if self.auth is not None and not (isinstance(self.auth, tuple) and len(self.auth) == 2
                                          and all(isinstance(part, str) for part in self.auth)):
            raise ValueError("auth is a (user, password) pair of strings")
        if self.auth is not None and self.token is not None:
            raise ValueError("give either auth or token, not both")
        check_timeout(self.timeout)
        if isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int) or self.max_bytes < 1:
            raise ValueError(f"max_bytes must be a positive whole number of bytes, got {self.max_bytes!r}")
        form(self.query)


def _basic(auth: tuple[str, str]) -> str:
    return base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()


def _scrub(text: str, q: Query) -> str:
    """Server text with this query's secrets blanked: some servers echo the request headers back."""
    secrets = [q.token, q.auth[1], _basic(q.auth)] if q.auth else [q.token]
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would re-send a redirected POST as a bodiless GET, credentials included: refuse the
    redirect and name the new URL instead."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()                                   # urllib closes it only when it follows
        raise FetchError(f"endpoint {_where(req.full_url)} redirects to {_clean(newurl)}: use that URL")


_OPENER = urllib.request.build_opener(_NoRedirect)


def _user_agent() -> str:
    from . import __version__  # here, not at the top: ttl3d/__init__ sets it after importing api
    return USER_AGENT.format(__version__)


def fetch(q: Query) -> tuple[bytes, str | None]:
    """POST the query as a form body and return the answer's bytes and media type (without
    parameters; None when the endpoint sent no Content-Type). Every failure is a FetchError naming
    the endpoint's host and path, never a credential."""
    headers = {"Accept": ACCEPT, "User-Agent": _user_agent(),
               "Content-Type": "application/x-www-form-urlencoded"}
    if q.token:
        headers["Authorization"] = "Bearer " + q.token
    elif q.auth:
        headers["Authorization"] = "Basic " + _basic(q.auth)
    req = urllib.request.Request(q.endpoint, data=urllib.parse.urlencode({"query": q.query}).encode(),
                                 headers=headers, method="POST")
    where = _where(q.endpoint)
    try:
        with _OPENER.open(req, timeout=q.timeout) as resp:
            body = resp.read(q.max_bytes + 1)
            media = resp.headers.get_content_type() if resp.headers.get("Content-Type") else None
            short = resp.length                       # bytes promised by Content-Length but never sent
    except urllib.error.HTTPError as e:
        first = " ".join(e.read(4096).decode("utf-8", "replace").split("\n", 1)[0].split())
        e.close()
        first = _scrub(first, q)[:200]
        raise FetchError(f"endpoint {where} answered {e.code}" + (f": {first}" if first else "")) from e
    except TimeoutError as e:
        raise FetchError(f"endpoint {where} did not answer within {q.timeout:g} s") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise FetchError(f"endpoint {where} did not answer within {q.timeout:g} s") from e
        raise FetchError(f"cannot reach {where}: {e.reason}") from e
    except (OSError, http.client.HTTPException) as e:       # a connection that broke off mid-answer
        raise FetchError(f"endpoint {where} broke off the answer: {e}") from e
    if len(body) > q.max_bytes:
        raise FetchError(f"endpoint {where} answered more than {q.max_bytes / 1e6:g} MB; "
                         "narrow the query or raise the limit (--max-mb, Query.max_bytes)")
    if short:
        raise FetchError(f"endpoint {where} broke off the answer after {len(body)} bytes")
    if media is not None and media not in RDF_MEDIA_TYPES:
        raise FetchError(f"endpoint {where} answered {media} instead of RDF")
    return body, media
