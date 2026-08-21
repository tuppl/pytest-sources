"""How the bracket of a fanned-out nodeid is built, and reading it back.

pytest joins parameter ids with "-", which is also legal in a directory name.
nodeid replaces that separator with "+" while sources are in use, and source
validation refuses sources containing it, so the source is always everything
before the first "+".
"""

from types import SimpleNamespace

import pytest

from pytest_sources._core import nodeid as _nodeid
from pytest_sources._core.nodeid import UNFANNED, source_of

SOURCE_IDS = {
    "submissions/alice",
    "submissions/alice2",
    "submissions/alice-alt",
    "submissions/my-source",
}


def make_sources(pytester, *names):
    for name in names:
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text("X = 1\n")


def collect(pytester, *args):
    result = pytester.runpytest("--collect-only", "-q", *args)
    return [line for line in result.outlines if "::" in line]


def collect_sources(pytester):
    return collect(pytester, "--sources", "submissions/*")


def brackets(nodeids):
    return {nodeid[nodeid.index("[") :] for nodeid in nodeids}


class TestIdConstruction:
    """How pytest builds the bracket of a fanned-out nodeid."""

    def test_source_id_is_the_whole_bracket_when_there_are_no_parameters(self, pytester):
        make_sources(pytester, "alice")
        pytester.makepyfile("def test_x(source): ...")

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[submissions/alice]")

    def test_a_parameter_is_appended_after_the_delimiter(self, pytester):
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[submissions/alice+1]")

    def test_every_parametrize_call_adds_another_delimiter(self, pytester):
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("mode", ["fast"])
            @pytest.mark.parametrize("n", [1])
            def test_x(source, n, mode): ...
            """
        )

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[submissions/alice+1+fast]")

    def test_values_within_one_parametrize_call_are_still_joined_with_a_dash(self, pytester):
        """Only the join between parametrize calls is replaced."""
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("a,b", [(1, 2)])
            def test_x(source, a, b): ...
            """
        )

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[submissions/alice+1-2]")

    def test_explicitly_given_parameter_ids_are_joined_the_same_way(self, pytester):
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [pytest.param(1, id="one")])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[submissions/alice+one]")

    def test_an_appended_parameter_is_distinct_from_a_dashed_source(self, pytester):
        make_sources(pytester, "alice", "alice-1")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        # Joined with "-" both of these would render as [submissions/alice-1].
        assert brackets(collect_sources(pytester)) == {
            "[submissions/alice+1]",
            "[submissions/alice-1+1]",
        }

    def test_unfanned_tests_are_joined_with_the_delimiter_too(self, pytester):
        """The patch is process-wide, so no_sources tests are affected as well."""
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.no_sources
            @pytest.mark.parametrize("mode", ["fast"])
            @pytest.mark.parametrize("n", [1])
            def test_x(n, mode): ...
            """
        )

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[1+fast]")


class TestSourceOf:
    """Reading a source back out of a nodeid."""

    def test_matches_a_lone_source(self):
        assert source_of("t.py::test_x[submissions/alice]", SOURCE_IDS) == "submissions/alice"

    def test_matches_when_the_test_has_further_parameters(self):
        assert source_of("t.py::test_x[submissions/alice+1]", SOURCE_IDS) == "submissions/alice"

    def test_matches_a_source_whose_name_contains_a_dash(self):
        assert source_of("t.py::test_x[submissions/my-source+1]", SOURCE_IDS) == "submissions/my-source"

    def test_matches_a_dashed_parameter_value(self):
        assert source_of("t.py::test_x[submissions/alice+a-b]", SOURCE_IDS) == "submissions/alice"

    def test_distinguishes_a_dashed_source_from_a_dashed_parameter(self):
        # Without the reserved delimiter both of these would read as
        # submissions/alice-alt.
        assert source_of("t.py::test_x[submissions/alice-alt+1]", SOURCE_IDS) == "submissions/alice-alt"
        assert source_of("t.py::test_x[submissions/alice+alt]", SOURCE_IDS) == "submissions/alice"

    def test_matches_a_source_another_plugin_parametrised_ahead_of(self):
        """A plugin whose generate hook runs before ours takes the front of the id."""
        assert source_of("t.py::test_x[w1+submissions/alice]", SOURCE_IDS) == "submissions/alice"

    def test_matches_a_source_with_parameters_either_side_of_it(self):
        assert source_of("t.py::test_x[w1+submissions/alice+1-2]", SOURCE_IDS) == "submissions/alice"

    def test_matches_a_source_in_the_last_position(self):
        assert source_of("t.py::test_x[w1+3+submissions/alice]", SOURCE_IDS) == "submissions/alice"

    def test_ignores_the_group_when_the_source_is_not_first(self):
        assert source_of("t.py::test_x[w1+submissions/alice]@db", SOURCE_IDS) == "submissions/alice"

    def test_unparametrised_test_belongs_to_no_source(self):
        assert source_of("t.py::test_x", SOURCE_IDS) == UNFANNED

    def test_unknown_parameter_belongs_to_no_source(self):
        assert source_of("t.py::test_x[3]", SOURCE_IDS) == UNFANNED

    def test_a_test_whose_parameters_name_no_source_belongs_to_none(self):
        assert source_of("t.py::test_x[w1+3+a-b]", SOURCE_IDS) == UNFANNED

    def test_matches_a_bare_nodeid_without_a_module_separator(self):
        assert source_of("test_x[submissions/alice]", SOURCE_IDS) == "submissions/alice"

    def test_ignores_brackets_in_the_file_path(self):
        assert source_of("dir[1]/t.py::test_x[submissions/alice]", SOURCE_IDS) == "submissions/alice"

    def test_ignores_the_group_xdist_appends_under_loadgroup(self):
        assert source_of("t.py::test_x[submissions/alice]@db", SOURCE_IDS) == "submissions/alice"

    def test_ignores_the_group_on_an_unfanned_test(self):
        assert source_of("t.py::test_x@db", SOURCE_IDS) == UNFANNED

    def test_ignores_a_group_name_containing_an_at_sign(self):
        assert source_of("t.py::test_x[submissions/alice]@a@b", SOURCE_IDS) == "submissions/alice"

    def test_keeps_a_source_containing_an_at_sign(self):
        assert source_of("t.py::test_x[submissions/al@ce]", SOURCE_IDS | {"submissions/al@ce"}) == "submissions/al@ce"


class TestDeclaredSource:
    """What a harness claims through pytest_sources_source_of."""

    def config(self, answer, asked=None):
        """A config whose plugin manager answers the hook, recording what it was asked."""

        def hook(nodeid):
            if asked is not None:
                asked.append(nodeid)
            return answer

        return SimpleNamespace(pluginmanager=SimpleNamespace(hook=SimpleNamespace(pytest_sources_source_of=hook)))

    def test_a_claim_places_an_id_that_names_no_source(self):
        assert source_of("checks/a.check::verify", SOURCE_IDS, self.config("submissions/alice")) == "submissions/alice"

    def test_a_claim_outside_the_run_is_ignored(self):
        assert source_of("checks/a.check::verify", SOURCE_IDS, self.config("submissions/ghost")) == UNFANNED

    def test_no_claim_leaves_the_id_unfanned(self):
        assert source_of("checks/a.check::verify", SOURCE_IDS, self.config(None)) == UNFANNED

    def test_an_id_naming_a_source_is_never_offered(self):
        asked: list[str] = []
        nodeid = "t.py::test_x[submissions/alice]"

        assert source_of(nodeid, SOURCE_IDS, self.config("submissions/alice2", asked)) == "submissions/alice"
        assert asked == []

    def test_the_group_is_dropped_before_the_hook_is_asked(self):
        """A harness knows its items by nodeid, not by the scope xdist schedules them in."""
        asked: list[str] = []

        source_of("checks/a.check::verify@db", SOURCE_IDS, self.config(None, asked))

        assert asked == ["checks/a.check::verify"]

    def test_without_a_config_there_is_nothing_to_ask(self):
        assert source_of("checks/a.check::verify", SOURCE_IDS) == UNFANNED


class TestMovedInternals:
    """What happens when pytest no longer has the private class we patch.

    CallSpec2.id is private, so a future pytest may rename or move it. Losing the
    delimiter costs isolation, never correctness, so it warns rather than fails.
    """

    def test_a_renamed_callspec_warns(self, monkeypatch):
        monkeypatch.delattr("_pytest.python.CallSpec2")

        with pytest.warns(pytest.PytestWarning, match="could not set the parameter id delimiter"):
            assert _nodeid._call_spec_class() is None

    def test_an_id_that_is_no_longer_a_property_warns(self, monkeypatch):
        monkeypatch.setattr("_pytest.python.CallSpec2", object)

        with pytest.warns(pytest.PytestWarning, match="could not set the parameter id delimiter"):
            assert _nodeid._call_spec_class() is None

    def test_the_warning_names_the_delimiter_in_use(self, monkeypatch):
        monkeypatch.setattr("_pytest.python.CallSpec2", object)
        monkeypatch.setattr(_nodeid, "_delimiter", "#")

        with pytest.warns(pytest.PytestWarning, match="'#'"):
            _nodeid._call_spec_class()

    def test_the_warning_names_the_join_ids_fall_back_to(self, monkeypatch):
        """A source containing the delimiter is rejected up front, so it cannot be
        the hazard. When the patch fails, ids join with pytest's "-" instead."""
        monkeypatch.setattr("_pytest.python.CallSpec2", object)

        with pytest.warns(pytest.PytestWarning, match="contains '-'"):
            _nodeid._call_spec_class()

    def test_patching_is_skipped_rather_than_half_applied(self, monkeypatch):
        monkeypatch.setattr("_pytest.python.CallSpec2", object)
        monkeypatch.setattr(_nodeid, "_original_id", None)

        with pytest.warns(pytest.PytestWarning):
            _nodeid._patch()

        assert _nodeid._original_id is None

    def test_ids_keep_pytests_own_separator_when_the_patch_is_skipped(self, pytester, monkeypatch):
        """The degraded run still works, it just cannot pin parametrised tests."""
        monkeypatch.setattr(_nodeid, "_patch", lambda: None)
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect_sources(pytester)

        assert nodeid.endswith("[submissions/alice-1]")
