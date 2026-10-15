"""ttl3d.table: CSV/TSV text and DataFrames read as tables, classified by header, turned into RDF."""
import pytest
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from ttl3d import table

B = table.DEFAULT_BASE


def csv(text, name="t.csv", columns=None):
    """A read and classified table."""
    t = table.parse(text, name)
    table.classify(t, table.check_columns(columns))
    return t


def graphs(*texts, prefixes=None, base=B, columns=None):
    made, _ = table.to_graphs([csv(t, f"t{i}.csv", columns) for i, t in enumerate(texts)],
                              prefixes or {}, base)
    return made


def m(local):
    return URIRef(B + local)


@pytest.mark.parametrize(("header", "delimiter"), [
    ("id,name,type", ","), ("id;name;type", ";"), ("id\tname\ttype", "\t"),
    ('"a,b";c', ";"),                 # a comma inside quotes does not count
    ("id;name,type", ","),            # a tie goes to the comma
    ("id", ","),                      # one column
])
def test_the_delimiter_is_guessed_from_the_header_line(header, delimiter):
    assert table._delimiter(header) == delimiter


def test_a_semicolon_table_reads_whole_cells():
    t = table.parse("id;name\n1;Smith, Jane\n", "t.csv")
    assert [c.header for c in t.columns] == ["id", "name"] and t.rows == [(2, ["1", "Smith, Jane"])]


def test_tsv_reads_tabs_even_when_the_header_has_commas(tmp_path):
    f = tmp_path / "t.tsv"
    f.write_text("id\tname, full\n1\tA, B\n", encoding="utf-8")
    for t in (table.read_path(f, "tsv"), table.read_bytes(f.read_bytes(), "tsv")):     # a file, stdin
        assert [c.header for c in t.columns] == ["id", "name, full"] and t.rows == [(2, ["1", "A, B"])]


def test_a_byte_order_mark_is_dropped_and_cells_are_trimmed():
    t = table.read_bytes("﻿id , name\n 1 ,  Alice \n".encode(), "csv")
    assert [c.header for c in t.columns] == ["id", "name"] and t.rows == [(2, ["1", "Alice"])]


def test_text_that_is_not_utf8_is_refused():
    with pytest.raises(table.TableError, match=r"^stdin: not UTF-8 text; save the table as UTF-8$"):
        table.read_bytes("id\nCaf\xe9\n".encode("latin-1"), "csv")


def test_blank_lines_and_empty_rows_are_skipped_and_lines_keep_their_numbers():
    t = table.parse('id,name\n\n,\n1,"two\nlines"\n2,B\n', "t.csv")
    assert t.rows == [(4, ["1", "two\nlines"]), (6, ["2", "B"])]


def test_a_row_with_more_cells_than_the_header_names_its_line():
    with pytest.raises(table.TableError, match=r"^t.csv: line 4: 3 cells, but the header has 2$"):
        table.parse("id,name\n\n1,A\n2,B,C\n", "t.csv")


def test_an_unclosed_quote_is_an_error_not_a_cell_that_swallows_the_file():
    with pytest.raises(table.TableError, match=r"^t.csv: line 2: unexpected end of data$"):
        table.parse('source,target,note\na,b,"open\nc,d,x\ne,f,y\n', "t.csv")
    assert table.parse('id,note\n1,a "quoted" word\n', "t.csv").rows == [(2, ["1", 'a "quoted" word'])]


def test_a_cell_over_the_csv_field_limit_is_a_one_line_error():
    with pytest.raises(table.TableError, match=r"^t.csv: line 2: field larger than field limit"):
        table.parse("id,note\n1," + "x" * 200_000 + "\n", "t.csv")


def test_extra_cells_that_are_empty_lose_nothing_and_are_allowed():
    assert table.parse("id,name\n1,A,,\n2\n", "t.csv").rows == [(2, ["1", "A"]), (3, ["2", ""])]


@pytest.mark.parametrize(("header", "name", "key", "group", "array"), [
    ("personId:ID(Person)", "personId", ":id", "Person", False),
    (":START_ID(Person)", "", ":start_id", "Person", False),
    (":END_ID", "", ":end_id", None, False),
    (":TYPE", "", ":type", None, False),
    (":LABEL", "", ":label", None, False),
    ("born:int", "born", "born", None, False),
    ("name:string", "name", "name", None, False),
    ("roles:string[]", "roles", "roles", None, True),
    ("x:IGNORE", "x", None, None, False),
    (":start_id", ":start_id", ":start_id", None, False),       # lower case: a plain name, still a known one
    ("rdfs:label", "rdfs:label", "rdfs:label", None, False),    # Neo4j kinds count in upper case only
    ("dc:type", "dc:type", "dc:type", None, False),
    ("ex:id", "ex:id", "ex:id", None, False),
    ("foaf:name", "foaf:name", "foaf:name", None, False),      # not a Neo4j kind: the colon is the name's
    ("a:int(b)", "a:int(b)", "a:int(b)", None, False),         # a group belongs to ID kinds only
    ("Weight", "Weight", "weight", None, False),
    ("", "", None, None, False),                               # an empty header is ignored
])
def test_headers_are_read_with_neo4j_import_syntax(header, name, key, group, array):
    c = table.column(header)
    assert (c.name, c.key, c.group, c.array) == (name, key, group, array)


def test_rdf_names_as_headers_mean_what_they_say():
    rdfs, dc = "http://www.w3.org/2000/01/rdf-schema#", "http://purl.org/dc/terms/"
    g, = graphs("id,rdfs:label,dc:type\nx,Ex,Thing\n", prefixes={rdfs: "rdfs", dc: "dc"})
    assert set(g) == {(m("x"), RDFS.label, Literal("Ex")), (m("x"), URIRef(dc + "type"), Literal("Thing"))}


def test_gephi_edge_headers_take_the_label_as_the_relation():
    t = csv("Source,Target,Type,Id,Label,Weight\na,b,Directed,0,likes,2\n")
    assert t.is_edges and t.roles["relation"] == 4
    (g,), _ = table.to_graphs([t], {}, B)
    assert (m("a"), m("likes"), m("b")) in g
    stmt = next(g.subjects(RDF.type, RDF.Statement))
    assert {(p, str(o)) for p, o in g.predicate_objects(stmt) if isinstance(o, Literal)} == {
        (m("Type"), "Directed"), (m("Id"), "0"), (m("Weight"), "2")}


def test_a_plain_type_column_is_the_relation_of_an_edge_table():
    g, = graphs("source,target,type\na,b,likes\n")
    assert (m("a"), m("likes"), m("b")) in g


def test_known_names_take_priority_in_order_and_the_rest_are_properties():
    t = csv("title,name,key,id\nT,N,K,I\n")
    assert t.roles["id"] == 3 and t.roles["label"] == 1         # id before key, name before title
    (g,), _ = table.to_graphs([t], {}, B)
    assert set(g) == {(m("I"), RDFS.label, Literal("N")), (m("I"), m("title"), Literal("T")),
                      (m("I"), m("key"), Literal("K"))}


def test_a_neo4j_property_graph_keeps_id_groups_apart():
    nodes = "personId:ID(Person),name,born:int,:LABEL\n1,Keanu,1964,Person;Actor\n"
    movies = "movieId:ID(Movie),title,:LABEL\n1,The Matrix,Movie\n"
    rels = ":START_ID(Person),:END_ID(Movie),:TYPE,roles:string[],note:IGNORE\n1,1,ACTED_IN,Neo;The One,x\n"
    g_people, g_movies, g_rels = graphs(nodes, movies, rels)
    keanu, matrix = m("Person/1"), m("Movie/1")
    assert set(g_people) == {(keanu, RDFS.label, Literal("Keanu")), (keanu, m("born"), Literal("1964")),
                             (keanu, RDF.type, m("Person")), (keanu, RDF.type, m("Actor"))}
    assert (matrix, RDFS.label, Literal("The Matrix")) in g_movies
    assert (keanu, m("ACTED_IN"), matrix) in g_rels
    stmt = next(g_rels.subjects(RDF.type, RDF.Statement))
    assert set(g_rels.objects(stmt, m("roles"))) == {Literal("Neo"), Literal("The One")}
    assert not set(g_rels.objects(stmt, m("note")))                       # :IGNORE is skipped


def test_an_apoc_export_holds_nodes_and_relationships_in_one_table():
    g, = graphs("_id,_labels,name,_start,_end,_type,since\n"
                "1,:Person:Actor,Alice,,,,\n2,:Person,Bob,,,,\n,,,1,2,KNOWS,2020\n",
                prefixes={"http://d.org/": ""})                # ":Person" must not resolve through ":"
    assert (m("1"), RDFS.label, Literal("Alice")) in g and (m("1"), m("KNOWS"), m("2")) in g
    assert set(g.objects(m("1"), RDF.type)) == {m("Person"), m("Actor")}
    assert set(g.objects(None, m("since"))) == {Literal("2020")}


def test_a_table_without_roles_says_what_it_found():
    with pytest.raises(table.TableError, match=r"^t.csv: no source and target columns and no id column "
                                               r"\(found: a, b\); name them, or map them with --columns$"):
        csv("a,b\n1,2\n")


def test_an_edge_needs_both_ends_and_a_node_needs_an_id():
    with pytest.raises(table.TableError, match=r"^t.csv: line 3: an edge needs both a source and a target$"):
        csv("source,target\na,b\na,\n")
    with pytest.raises(table.TableError, match=r"^t.csv: line 2: no id$"):
        csv("id,name\n,Nameless\n")


def test_a_table_without_rows_is_an_empty_source_whatever_its_header():
    assert [len(g) for g in graphs("a,b\n", "")] == [0, 0]


def test_a_mapped_column_is_not_taken_by_another_roles_known_names():
    g, = graphs("id,name,category\n1,Alice,Person\n", columns={"type": "name"})
    assert (m("1"), RDF.type, m("Alice")) in g                    # the mapping wins, name is no label
    assert set(g.objects(m("1"), RDFS.label)) == {Literal("1")}


def test_columns_map_roles_to_headers_and_replace_the_known_names():
    t = csv("from_id,to_id,source\na,b,web\n", columns={"source": "FROM_ID", "target": "to_id"})
    (g,), _ = table.to_graphs([t], {}, B)
    assert (m("a"), m("related"), m("b")) in g                     # no relation column: csv:related
    assert set(g.objects(None, m("source"))) == {Literal("web")}   # "source" is just a property now


@pytest.mark.parametrize(("columns", "message"), [
    ({"srcc": "x"}, ("unknown column role 'srcc'; roles are id, label, type, description, source, target, "
                     "relation")),
    ({"source": " "}, "the column for source must be a non-empty header, got ' '"),
])
def test_bad_columns_are_refused(columns, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        table.check_columns(columns)


def test_a_mapped_header_that_no_table_has_is_an_error():
    t = csv("id\n1\n")
    with pytest.raises(ValueError, match=r"^no table has the column 'from_id' that source=from_id names$"):
        table.check_mapped({"source": "from_id"}, [t])


@pytest.mark.parametrize("base", ["x", "http://e/x", "http://e/a b/", "", 3])
def test_a_base_must_be_an_absolute_iri_ending_in_a_separator(base):
    with pytest.raises(ValueError, match="^base must be an absolute IRI ending in /, # or :"):
        table.check_base(base)


def test_ids_written_as_iris_or_bound_curies_are_used_as_such_and_the_rest_are_minted():
    g, = graphs("source,target\n<urn:a:b>,http://e.org/x\nex:a,Person:1\n:c,New York\n",
                prefixes={"http://e.org/": "ex", "http://d.org/": ""})
    assert (URIRef("urn:a:b"), m("related"), URIRef("http://e.org/x")) in g
    assert (URIRef("http://e.org/a"), m("related"), m("Person:1")) in g       # Person is no bound prefix
    assert (URIRef("http://d.org/c"), m("related"), m("New%20York")) in g


def test_an_empty_bracket_pair_is_a_plain_id_in_a_table():
    g, = graphs("id\n<>\n")                    # --focus calls it "an empty term"; a table mints it
    assert set(g) == {(m("%3C%3E"), RDFS.label, Literal("<>"))}


def test_minting_is_one_to_one():
    ids = ["a/b", "a%2Fb", "a b", "a%20b", "a#b", "a?b", 'a"b', "é"]
    g, = graphs("id\n" + "\n".join(f'"{i}"' if '"' not in i else '"a""b"' for i in ids) + "\n")
    minted = sorted(str(s) for s in g.subjects(RDFS.label, None))
    assert len(minted) == len(ids) and m("é") in set(g.subjects())
    assert {str(o) for o in g.objects(None, RDFS.label)} == set(ids)       # every id reads as written


def test_an_id_that_cannot_be_an_iri_names_its_line():
    with pytest.raises(table.TableError, match=r"^t0.csv: line 2: '<a b>' cannot be an IRI: "
                                               r"it contains ' '$"):
        graphs("id\n<a b>\n")


def test_vocabulary_joins_rdf_terms_when_bound_and_is_minted_with_underscores_otherwise():
    g, = graphs("id,type,foaf:name,works at\nx,foaf:Person,X,ACME\n",
                prefixes={"http://xmlns.com/foaf/0.1/": "foaf"})
    foaf = "http://xmlns.com/foaf/0.1/"
    assert set(g) == {(m("x"), RDF.type, URIRef(foaf + "Person")),
                      (m("x"), URIRef(foaf + "name"), Literal("X")),
                      (m("x"), m("works_at"), Literal("ACME")),
                      (m("x"), RDFS.label, Literal("x"))}


def test_a_minted_node_gets_its_id_as_label_from_its_node_table_else_from_its_first_mention():
    edges = "source,target\na,b\nb,<urn:x:c>\n"
    nodes = "id,name\nb,\n"                        # b is listed without a label
    g_edges, g_nodes = graphs(edges, nodes)
    assert (m("a"), RDFS.label, Literal("a")) in g_edges            # only the edge table mentions a
    assert (m("b"), RDFS.label, Literal("b")) in g_nodes            # b has a node row: labelled there
    assert not set(g_edges.objects(m("b"), RDFS.label))
    assert not set(g_edges.objects(URIRef("urn:x:c"), RDFS.label))  # an IRI id gets no label


def test_a_node_row_label_replaces_the_id_label():
    g_edges, g_nodes = graphs("source,target\na,b\n", "id,label\na,Alpha\n")
    assert set(g_nodes.objects(m("a"), RDFS.label)) == {Literal("Alpha")}
    assert not set(g_edges.objects(m("a"), RDFS.label))


def test_only_an_edge_row_with_property_cells_is_reified():
    g, = graphs("source,target,relation,since\na,b,knows,\na,c,knows,2020\n")
    stmts = list(g.subjects(RDF.type, RDF.Statement))
    assert len(stmts) == 1 and isinstance(stmts[0], BNode)
    s = stmts[0]
    assert (g.value(s, RDF.subject), g.value(s, RDF.predicate), g.value(s, RDF.object)) == (
        m("a"), m("knows"), m("c"))
    assert g.value(s, m("since")) == Literal("2020")


def test_an_edge_property_named_after_the_statements_own_terms_is_minted():
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    g, = graphs(f"source,target,rdf:subject,<{rdf}type>\na,b,x,y\n", prefixes={rdf: "rdf"})
    stmt = next(g.subjects(RDF.type, RDF.Statement))
    assert list(g.objects(stmt, RDF.subject)) == [m("a")]           # the statement stays whole
    assert g.value(stmt, m("rdf:subject")) == Literal("x")
    assert g.value(stmt, m(f"%3C{rdf.replace('/', '%2F').replace('#', '%23')}type%3E")) == Literal("y")


def test_a_custom_base_names_minted_ids_and_vocabulary():
    g, = graphs("source,target,relation\na,b,\n", base="http://example.org/g#")
    assert set(g) >= {(URIRef("http://example.org/g#a"), URIRef("http://example.org/g#related"),
                       URIRef("http://example.org/g#b"))}


class Frame:
    """Just enough of a DataFrame: columns and to_csv(index=False)."""
    columns = ("id", "name")

    def to_csv(self, index=True):
        assert index is False
        return "id,name\n1,One\n"


def test_a_dataframe_is_read_through_to_csv_with_commas():
    assert table.is_frame(Frame()) and not table.is_frame("x.csv")
    t = table.read_frame(Frame(), "people")
    assert t.name == "people" and t.rows == [(2, ["1", "One"])]


def test_windows_line_endings_read_like_unix_ones():
    t = table.read_bytes(b"id,name\r\n1,A\r\n\r\n2,B\r\n", "csv")
    assert t.rows == [(2, ["1", "A"]), (4, ["2", "B"])]


def test_a_repeated_header_serves_its_role_once_and_is_a_property_after_that():
    g, = graphs("id,name,name\n1,A,B\n")
    assert set(g) == {(m("1"), RDFS.label, Literal("A")), (m("1"), m("name"), Literal("B"))}


def test_spaces_around_an_id_do_not_keep_two_tables_apart():
    g_nodes, g_edges = graphs("id, name\nalice , Alice\n", "source, target\n alice,bob\n")
    assert (m("alice"), RDFS.label, Literal("Alice")) in g_nodes
    assert (m("alice"), m("related"), m("bob")) in g_edges


class Indexed:
    """A frame whose ids sit in a named index, as after set_index("id")."""
    columns = ("name",)

    class index:                      # pandas' attribute name
        names = ("id",)

    def to_csv(self, index=True):
        return "id,name\n1,One\n" if index else "name\nOne\n"


def test_a_dataframe_keeps_a_named_index_as_a_column():
    t = table.read_frame(Indexed(), "people")
    assert [c.header for c in t.columns] == ["id", "name"] and t.rows == [(2, ["1", "One"])]
