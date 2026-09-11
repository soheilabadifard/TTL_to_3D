"""tools/compare_pages.py: pages built on different machines must be byte-identical except for
the pinned layout coordinates, which drift by a few tenths across scipy and BLAS builds."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "compare_pages", Path(__file__).resolve().parents[1] / "tools" / "compare_pages.py")
compare_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_pages)

PAGE = ('<script>const DATA = {"nodes": [{"id": "a", "x": -1.5, "y": 2.25, "z": 0.0, "x2": 3.0, "y2": -4.0, '
        '"props": {"x": "not a coordinate", "y2": "1.5 kg"}}], "links": []};</script>\n')


def test_coordinates_are_masked_and_collected_in_order_while_string_values_stay():
    masked, coords = compare_pages.strip_coordinates(PAGE)
    assert coords == [-1.5, 2.25, 0.0, 3.0, -4.0]
    assert '"x": #' in masked and '"y2": #' in masked
    assert '"x": "not a coordinate"' in masked and '"y2": "1.5 kg"' in masked


def test_identical_pages_compare_equal():
    ok, note = compare_pages.compare(PAGE, PAGE)
    assert ok and note == "identical"


def test_pages_differing_only_in_coordinates_within_tolerance_pass_and_report_the_drift():
    other = PAGE.replace('"x": -1.5', '"x": -1.2').replace('"y2": -4.0', '"y2": -4.4')
    ok, note = compare_pages.compare(PAGE, other, tolerance=1.0)
    assert ok and note == "coordinates drift by up to 0.40"


def test_coordinate_drift_beyond_the_tolerance_fails():
    other = PAGE.replace('"y": 2.25', '"y": 4.25')
    ok, note = compare_pages.compare(PAGE, other, tolerance=1.0)
    assert not ok and "2.00" in note and "tolerance" in note


def test_any_other_difference_fails_and_names_where():
    other = PAGE.replace('"id": "a"', '"id": "b"')
    ok, note = compare_pages.compare(PAGE, other)
    assert not ok and "offset" in note and '"b"' in note


def test_main_compares_every_page_of_the_first_directory_against_the_others(tmp_path, capsys):
    dirs = [tmp_path / d for d in ("linux", "windows", "mac")]
    for d in dirs:
        d.mkdir()
        (d / "solar-3d.html").write_text(PAGE, encoding="utf-8")
        (d / "solar-force.html").write_text("<p>same</p>", encoding="utf-8")
    assert compare_pages.main([str(d) for d in dirs]) == 0
    (dirs[2] / "solar-force.html").write_text("<p>other</p>", encoding="utf-8")
    assert compare_pages.main([str(d) for d in dirs]) == 1
    out = capsys.readouterr().out
    assert "solar-force.html" in out and "mac" in out
