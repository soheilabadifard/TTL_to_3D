"""How a written term becomes an IRI: one rule for --focus and --attribute-preds terms and for the ids
and vocabulary of tables. `<...>` and anything holding `://` are IRIs as written; `prefix:local` goes
through the prefixes the inputs bind. What happens to a term that is none of these is the caller's
choice: graph.resolve_terms refuses it, ttl3d.table mints it.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from rdflib import URIRef

NOT_IN_IRI = re.compile(r'[\x00-\x20<>"{}|\\^`]')   # what Turtle's IRIREF excludes; rdflib logs about most


def by_prefix(prefixes: Mapping[str, str]) -> dict[str, str]:
    """{prefix: namespace} from a Dataset's {namespace: prefix}; the first namespace bound to a
    prefix wins, as in the bindings themselves."""
    out: dict[str, str] = {}
    for ns, prefix in prefixes.items():
        out.setdefault(prefix, ns)
    return out


def written(term: str, namespaces: Mapping[str, str]) -> URIRef | None:
    """The IRI a term writes: `<iri>`, anything with `://`, or `prefix:local` with a prefix in
    `namespaces` ({prefix: namespace}); None for any other term. ValueError when the IRI would hold
    a character Turtle's IRIREF excludes."""
    if term.startswith("<") and term.endswith(">") and len(term) > 2:
        iri = term[1:-1]
    elif "://" in term:
        iri = term
    else:
        prefix, colon, rest = term.partition(":")
        if not colon or prefix not in namespaces:
            return None
        iri = namespaces[prefix] + rest
    if (bad := NOT_IN_IRI.search(iri)):
        raise ValueError(f"{term!r} cannot be an IRI: it contains {bad.group()!r}")
    return URIRef(iri)
