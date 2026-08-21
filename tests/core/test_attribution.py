from types import SimpleNamespace

import pytest

from pytest_sources._core.attribution import attributed, record, source_map
from pytest_sources._core.discover import UNIVERSE
from pytest_sources._core.source import Source


def item_with(nodeid, source):
    """A collected item whose callspec carries the given source value."""
    return SimpleNamespace(nodeid=nodeid, callspec=SimpleNamespace(params={"source": source}))


def rows(result):
    """The counts body of the sources section, keyed by source."""
    lines = result.outlines
    start = next(i for i, line in enumerate(lines) if line.startswith("=") and " sources " in line)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("="):
            break
        body.append(line)
    return {line.split()[0]: line.split()[1:5] for line in body[1:]}


class TestRecording:
    """What collection puts into the map."""

    @pytest.fixture
    def config(self, pytester):
        config = pytester.parseconfig()
        config.stash[UNIVERSE] = [Source(path=pytester.path / "sources" / "good", id="sources/good")]
        return config

    def test_a_source_object_is_recorded_by_its_id(self, pytester, config):
        source = Source(path=pytester.path / "sources" / "good", id="sources/good")

        record([item_with("test_a.py::test_one[sources/good]", source)], config)

        assert source_map(config) == {"test_a.py::test_one[sources/good]": "sources/good"}

    def test_a_string_matching_a_universe_id_is_recorded(self, config):
        record([item_with("test_a.py::test_one[sources/good-x]", "sources/good")], config)

        assert source_map(config) == {"test_a.py::test_one[sources/good-x]": "sources/good"}

    def test_a_string_naming_an_unknown_source_is_not_recorded(self, config):
        record([item_with("test_a.py::test_one[sources/ghost-x]", "sources/ghost")], config)

        assert source_map(config) == {}

    def test_an_item_without_a_callspec_is_passed_over(self, config):
        record([SimpleNamespace(nodeid="test_a.py::test_one")], config)

        assert source_map(config) == {}


class TestLookup:
    """What a reader gets back out of the map."""

    def test_a_mapped_value_outside_the_universe_is_ignored(self):
        mapping = {"test_a.py::test_one[sources/gone-x]": "sources/gone"}

        assert attributed("test_a.py::test_one[sources/gone-x]", mapping, {"sources/good"}) == ""

    def test_a_loadgroup_suffix_does_not_hide_the_entry(self):
        mapping = {"test_a.py::test_one[sources/good-x]": "sources/good"}

        assert (
            attributed("test_a.py::test_one[sources/good-x]@sources/good+0", mapping, {"sources/good"})
            == "sources/good"
        )


class TestPrecedence:
    """The map's answer beats the one parsed out of the id."""

    def test_the_map_wins_over_a_misleading_id(self, pytester):
        for name in ("alpha", "beta"):
            (pytester.path / "sources" / name).mkdir(parents=True)
        pytester.makeconftest(
            """
            def pytest_generate_tests(metafunc):
                if "case" in metafunc.fixturenames:
                    metafunc.parametrize("source,case", [("sources/alpha", "one")], ids=["sources/beta"])
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.no_sources
            def test_labelled_as_the_other(source, case): ...
            """
        )

        result = pytester.runpytest("--sources", "sources/*", "-n", "0")

        result.assert_outcomes(passed=1)
        assert rows(result) == {
            "sources/alpha": ["1", "0", "0", "0"],
            "sources/beta": ["0", "0", "0", "0"],
        }

    def test_a_parameter_naming_no_known_source_attributes_nothing(self, pytester):
        (pytester.path / "sources" / "real").mkdir(parents=True)
        pytester.makeconftest(
            """
            def pytest_generate_tests(metafunc):
                if "case" in metafunc.fixturenames:
                    metafunc.parametrize("source,case", [("sources/ghost", "one")])
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.no_sources
            def test_of_no_source(source, case): ...
            """
        )

        result = pytester.runpytest("--sources", "sources/*", "-n", "0")

        result.assert_outcomes(passed=1)
        assert rows(result) == {
            "sources/real": ["0", "0", "0", "0"],
            "unattributed": ["1", "0", "0", "0"],
        }


class TestUnderXdist:
    """Workers collect for themselves, so each builds its own map."""

    def test_a_worker_spends_the_budget_from_its_own_map(self, pytester):
        for name in ("good", "slow"):
            (pytester.path / "sources" / name).mkdir(parents=True)
        pytester.makeconftest(
            """
            def pytest_generate_tests(metafunc):
                if "case" in metafunc.fixturenames:
                    pairs = [(s, c) for s in ("sources/good", "sources/slow") for c in ("alpha", "beta")]
                    metafunc.parametrize("source,case", pairs)
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.no_sources
            def test_combined(source, case):
                assert source != "sources/slow"
            """
        )

        result = pytester.runpytest("--sources", "sources/*", "-n", "2", "--sources-maxfail=1")

        result.assert_outcomes(passed=2, failed=1, skipped=1)
