"""ttl3d.sparql: a CONSTRUCT or DESCRIBE result fetched from a SPARQL endpoint."""
import urllib.parse

import pytest

from ttl3d import load, sparql

CONSTRUCT = "PREFIX ex: <http://example.org/q#> CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"


def test_form_reads_the_first_word_after_the_prologue():
    assert sparql.form("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }") == "CONSTRUCT"
    assert sparql.form("describe <http://example.org/x>") == "DESCRIBE"
    assert sparql.form("PREFIX ex: <http://e/#> BASE <http://b/#x>\n construct {} where {}") == "CONSTRUCT"
    assert sparql.form("# a comment first\n  CONSTRUCT {} WHERE {}") == "CONSTRUCT"
    assert sparql.form("PREFIX ex: <http://e/>#a glued comment\nCONSTRUCT {} WHERE {}") == "CONSTRUCT"
    # a # or a keyword inside an IRI is neither a comment nor a form
    assert sparql.form("PREFIX ex: <http://e/#SELECT> CONSTRUCT {} WHERE {}") == "CONSTRUCT"
    # a store's own pragma is the endpoint's to judge
    assert sparql.form("DEFINE input:inference 'x' CONSTRUCT {} WHERE {}") == "DEFINE"


@pytest.mark.parametrize(("query", "message"), [
    ("SELECT * WHERE { ?s ?p ?o }", "the query must be CONSTRUCT or DESCRIBE, not SELECT"),
    ("ASK { ?s ?p ?o }", "the query must be CONSTRUCT or DESCRIBE, not ASK"),
    ("PREFIX ex: <http://e/#> INSERT DATA { ex:a ex:p ex:b }",
     "the query must be CONSTRUCT or DESCRIBE, not INSERT"),
    ("WITH <http://g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
     "the query must be CONSTRUCT or DESCRIBE, not WITH"),
    ("", "the query is empty"),
    ("# only a comment\n", "the query is empty"),
])
def test_form_refuses_results_booleans_updates_and_empty_text(query, message):
    with pytest.raises(ValueError, match=message):
        sparql.form(query)


def test_prefixes_come_from_the_prologue_only_resolved_against_base():
    q = "prefix ex: <http://e/#> PREFIX : <http://d/> # PREFIX c: <http://no/>\nPREFIX ex: <http://dup/>"
    assert sparql.prefixes_in(q) == {"ex": "http://e/#", "": "http://d/"}
    dotted = "PREFIX my-ns.v2: <http://m/> CONSTRUCT {} WHERE {}"
    assert sparql.prefixes_in(dotted) == {"my-ns.v2": "http://m/"}
    relative = "BASE <http://x/y/> PREFIX ex: <rel/> CONSTRUCT {} WHERE {}"
    assert sparql.prefixes_in(relative) == {"ex": "http://x/y/rel/"}
    body = 'PREFIX a: <http://a/> CONSTRUCT { ?s ?p "x # PREFIX b: <http://b/>" } WHERE {}'
    assert sparql.prefixes_in(body) == {"a": "http://a/"}          # nothing after the prologue counts


def test_host_is_the_hostname_without_user_info_or_the_endpoint_itself():
    assert sparql.host("https://user:pw@query.wikidata.org/sparql") == "query.wikidata.org"
    assert sparql.host("not a url") == "not a url"


@pytest.mark.parametrize(("change", "message"), [
    ({"endpoint": "file:///etc/hosts"}, "the endpoint must be an http:// or https:// URL with a host name"),
    ({"endpoint": "https://bob:pw@h.org/sparql"}, "the endpoint URL must not carry credentials"),
    ({"auth": "bob:pw"}, "auth is a"),
    ({"auth": ("bob", "pw"), "token": "tok"}, "give either auth or token, not both"),
    ({"timeout": 0}, "timeout must be a positive number of seconds"),
    ({"timeout": float("inf")}, "timeout must be a positive number of seconds"),
    ({"max_bytes": 0}, "max_bytes must be a positive whole number of bytes"),
    ({"query": "SELECT * WHERE {}"}, "not SELECT"),
])
def test_an_invalid_query_cannot_be_built(change, message):
    with pytest.raises(ValueError, match=message) as e:
        sparql.Query(**{"endpoint": "https://h.org/sparql", "query": CONSTRUCT, **change})
    assert "pw" not in str(e.value) or "PASSWORD" in str(e.value)       # the URL's password is never echoed


def test_fetch_posts_the_form_body_with_the_accept_and_user_agent_headers(endpoint):
    body, media = sparql.fetch(sparql.Query(endpoint.url + "/sparql", CONSTRUCT))
    assert media == "text/turtle" and b"ex:a ex:p ex:b" in body
    path, headers, sent = endpoint.requests[0]
    assert path == "/sparql" and headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert urllib.parse.parse_qs(sent.decode()) == {"query": [CONSTRUCT]}
    assert headers["Accept"] == sparql.ACCEPT and "json" not in headers["Accept"]
    assert headers["User-Agent"].startswith("ttl3d/")
    assert "github.com/soheilabadifard/TTL_to_3D" in headers["User-Agent"]


@pytest.mark.parametrize(("path", "media", "triples"), [
    ("/sparql", "text/turtle", 2), ("/nt", "application/n-triples", 1), ("/notype", None, 2)])
def test_the_answer_parses_by_its_media_type_and_as_turtle_without_one(endpoint, path, media, triples):
    body, got = sparql.fetch(sparql.Query(endpoint.url + path, CONSTRUCT))
    assert got == media
    assert len(load.parse_data(body, got or "text/turtle", "q")) == triples


def test_basic_and_bearer_credentials_reach_the_endpoint(endpoint):
    sparql.fetch(sparql.Query(endpoint.url + "/auth", CONSTRUCT, auth=("bob", "s3cret")))
    sparql.fetch(sparql.Query(endpoint.url + "/auth", CONSTRUCT, token="tok123"))
    sent = [h["Authorization"] for _, h, _ in endpoint.requests]
    assert sent == ["Basic Ym9iOnMzY3JldA==", "Bearer tok123"]
    with pytest.raises(sparql.FetchError) as e:
        sparql.fetch(sparql.Query(endpoint.url + "/auth", CONSTRUCT))
    assert str(e.value) == "endpoint 127.0.0.1/auth answered 401"


@pytest.mark.parametrize("credentials", [{"auth": ("bob", "s3cret")}, {"token": "tok123"}])
def test_server_text_that_echoes_the_credentials_is_blanked(endpoint, credentials):
    with pytest.raises(sparql.FetchError) as e:
        sparql.fetch(sparql.Query(endpoint.url + "/echo", CONSTRUCT, **credentials))
    message = str(e.value)
    assert message.startswith("endpoint 127.0.0.1/echo answered 500: echo: ") and message.endswith("***")
    assert "s3cret" not in message and "tok123" not in message and "Ym9iOnMzY3JldA" not in message


def test_repr_and_str_hide_the_credentials():
    basic = sparql.Query("https://h.org/sparql", CONSTRUCT, auth=("bob", "s3cret"))
    bearer = sparql.Query("https://h.org/sparql", CONSTRUCT, token="tok123")
    for q in (basic, bearer):
        assert "s3cret" not in repr(q) and "tok123" not in repr(q) and "s3cret" not in str(q)
    assert basic.auth == ("bob", "s3cret") and bearer.token == "tok123"      # still usable


def test_an_http_error_names_the_status_and_the_first_line_of_the_body(endpoint):
    assert issubclass(sparql.FetchError, ValueError)                       # the CLI's handler catches it
    with pytest.raises(sparql.FetchError) as e:
        sparql.fetch(sparql.Query(endpoint.url + "/500", CONSTRUCT))
    assert str(e.value) == "endpoint 127.0.0.1/500 answered 500: Virtuoso 37000 Error SP030: SPARQL compiler"


@pytest.mark.parametrize(("path", "media"), [("/html", "text/html"), ("/jsonld", "application/ld+json")])
def test_a_non_rdf_or_json_ld_answer_is_refused_by_its_media_type(endpoint, path, media):
    # JSON-LD is refused on purpose: its parser would fetch a remote @context outside fetch's rules
    with pytest.raises(sparql.FetchError) as e:
        sparql.fetch(sparql.Query(endpoint.url + path, CONSTRUCT))
    assert str(e.value) == f"endpoint 127.0.0.1{path} answered {media} instead of RDF"


def test_a_slow_endpoint_hits_the_timeout(endpoint):
    with pytest.raises(sparql.FetchError, match=r"endpoint 127.0.0.1/slow did not answer within 0.5 s"):
        sparql.fetch(sparql.Query(endpoint.url + "/slow", CONSTRUCT, timeout=0.5))


def test_an_unreachable_endpoint_is_a_clean_error():
    with pytest.raises(sparql.FetchError, match=r"cannot reach 127.0.0.1/sparql: "):
        sparql.fetch(sparql.Query("http://127.0.0.1:9/sparql", CONSTRUCT, timeout=5))


def test_a_redirect_is_refused_and_names_the_new_url_without_its_secrets(endpoint):
    with pytest.raises(sparql.FetchError) as e:
        sparql.fetch(sparql.Query(endpoint.url + "/moved", CONSTRUCT, auth=("bob", "s3cret")))
    assert str(e.value) == f"endpoint 127.0.0.1/moved redirects to {endpoint.url}/sparql: use that URL"
    assert [path for path, _, _ in endpoint.requests] == ["/moved"]     # the credentials never followed it


def test_an_answer_over_the_limit_is_refused(endpoint):
    with pytest.raises(sparql.FetchError) as e:
        sparql.fetch(sparql.Query(endpoint.url + "/big", CONSTRUCT, max_bytes=1000))
    assert str(e.value) == ("endpoint 127.0.0.1/big answered more than 0.001 MB; "
                            "narrow the query or raise the limit (--max-mb, Query.max_bytes)")
    assert sparql.fetch(sparql.Query(endpoint.url + "/sparql", CONSTRUCT, max_bytes=1000))[1] == "text/turtle"


def test_an_answer_cut_short_is_an_error_not_a_smaller_graph(endpoint):
    with pytest.raises(sparql.FetchError, match="endpoint 127.0.0.1/cut broke off the answer"):
        sparql.fetch(sparql.Query(endpoint.url + "/cut", CONSTRUCT))
