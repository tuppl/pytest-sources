import re

import pytest

from pytest_sources._core import source as source_module
from pytest_sources._core.discover import SOURCES
from pytest_sources._core.nodeid import DEFAULT


@pytest.fixture
def submission_dirs(pytester):
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    return pytester


class TestConfigure:
    """What pytest_configure stashes, registers and rejects."""

    def test_configure_stashes_discovered_directories(self, submission_dirs):
        config = submission_dirs.parseconfigure("--sources", "submissions/*")
        assert [source.path for source in config.stash[SOURCES]] == [
            submission_dirs.path / "submissions" / "alice",
            submission_dirs.path / "submissions" / "bob",
        ]

    def test_configure_stashes_directories_from_ini(self, submission_dirs):
        submission_dirs.makeini("[pytest]\nsources = submissions/*\n")
        config = submission_dirs.parseconfigure()
        assert [source.path for source in config.stash[SOURCES]] == [
            submission_dirs.path / "submissions" / "alice",
            submission_dirs.path / "submissions" / "bob",
        ]

    def test_configure_stashes_root_relative_ids(self, submission_dirs):
        config = submission_dirs.parseconfigure("--sources", "submissions/*")
        assert [source.id for source in config.stash[SOURCES]] == [
            "submissions/alice",
            "submissions/bob",
        ]

    def test_command_line_overrides_ini(self, submission_dirs):
        submission_dirs.makeini("[pytest]\nsources = submissions/*\n")
        config = submission_dirs.parseconfigure("--sources", "submissions/alice")
        assert [source.path for source in config.stash[SOURCES]] == [submission_dirs.path / "submissions" / "alice"]

    def test_nothing_is_stashed_without_sources(self, submission_dirs):
        assert SOURCES not in submission_dirs.parseconfigure().stash

    def test_glob_matching_nothing_is_a_usage_error(self, submission_dirs):
        with pytest.raises(pytest.UsageError, match=re.escape("matched nothing: 'nope/*'")):
            submission_dirs.parseconfigure("--sources", "nope/*")

    def test_markers_are_registered(self, pytester):
        result = pytester.runpytest("--markers")
        result.stdout.fnmatch_lines(["@pytest.mark.sources*", "@pytest.mark.no_sources*"])

    def test_a_source_containing_the_delimiter_is_rejected(self, pytester):
        (pytester.path / "submissions" / f"a{DEFAULT}b").mkdir(parents=True)

        with pytest.raises(pytest.UsageError, match="may not appear in a source path"):
            pytester.parseconfigure("--sources", "submissions/*")

    def test_the_sources_marker_rejects_the_delimiter_too(self, pytester):
        (pytester.path / "submissions" / f"a{DEFAULT}b").mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.sources("submissions/*")
            def test_x(source): ...
            """
        )

        result = pytester.runpytest()
        result.stderr.fnmatch_lines(["*may not appear in a source path*"])
        assert result.ret != 0

    def test_sources_sharing_an_id_are_rejected(self, pytester, monkeypatch):
        monkeypatch.setattr(source_module, "_relative_id", lambda path, root: path.name)
        for parent in ("submissions", "other"):
            (pytester.path / parent / "alice").mkdir(parents=True)

        with pytest.raises(pytest.UsageError, match="must have distinct ids"):
            pytester.parseconfigure("--sources", "submissions/*", "--sources", "other/*")


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


class TestPatching:
    """Replacing pytest's separator, and putting it back."""

    def test_ids_are_untouched_without_sources(self, pytester):
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("mode", ["fast"])
            @pytest.mark.parametrize("n", [1])
            def test_x(n, mode): ...
            """
        )

        (nodeid,) = collect(pytester)
        assert nodeid.endswith("[1-fast]")

    def test_sources_from_the_ini_file_also_change_the_delimiter(self, pytester):
        make_sources(pytester, "alice")
        pytester.makeini("[pytest]\nsources = submissions/*\n")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect(pytester)
        assert nodeid.endswith("[submissions/alice+1]")

    def test_the_original_delimiter_is_restored_on_unconfigure(self, pytester):
        """Nested in-process runs must not leak the patch into the outer session."""
        from _pytest.python import CallSpec2

        before = CallSpec2.id

        make_sources(pytester, "alice")
        pytester.makepyfile("def test_x(source): ...")
        collect_sources(pytester)

        assert CallSpec2.id is before
        assert CallSpec2(params={}, indices={}, _arg2scope={}, _idlist=["a", "b"]).id == "a-b"
