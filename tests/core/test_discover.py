import re

import pytest

from pytest_sources._core.discover import SOURCES, discover, resolve, universe


@pytest.fixture
def tree(tmp_path):
    root = tmp_path.resolve()
    for path in (
        "submissions/zoe",
        "submissions/alice/pkg",
        "submissions/bob",
        "submissions/carol_alt",
        "other/alice",
    ):
        (root / path).mkdir(parents=True)
    (root / "submissions/README.md").touch()
    (root / "submissions/.git").mkdir()
    return root


@pytest.fixture
def submission_dirs(pytester):
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    return pytester


def relative(paths, root):
    return [str(p.relative_to(root)) for p in paths]


class TestResolve:
    """Turning the option into a cached list of sources."""

    def test_resolve_returns_the_sources_named_by_the_option(self, submission_dirs):
        config = submission_dirs.parseconfig("--sources", "submissions/*")

        assert [source.id for source in resolve(config)] == [
            "submissions/alice",
            "submissions/bob",
        ]

    def test_resolve_reads_the_ini_when_the_option_is_absent(self, submission_dirs):
        submission_dirs.makeini("[pytest]\nsources = submissions/*\n")
        config = submission_dirs.parseconfig()

        assert [source.id for source in resolve(config)] == [
            "submissions/alice",
            "submissions/bob",
        ]

    def test_resolve_prefers_the_option_over_the_ini(self, submission_dirs):
        submission_dirs.makeini("[pytest]\nsources = submissions/*\n")
        config = submission_dirs.parseconfig("--sources", "submissions/alice")

        assert [source.id for source in resolve(config)] == ["submissions/alice"]

    def test_resolve_yields_nothing_when_no_sources_are_configured(self, pytester):
        config = pytester.parseconfig()

        assert resolve(config) == []
        assert SOURCES not in config.stash

    def test_resolve_stashes_what_it_found(self, submission_dirs):
        config = submission_dirs.parseconfig("--sources", "submissions/*")
        sources = resolve(config)

        assert config.stash[SOURCES] == sources

    def test_resolve_expands_the_globs_only_once(self, submission_dirs, monkeypatch):
        """The result is cached because _workers and _schedule both ask for it.

        Without the cache the globs would be expanded again for every caller, and a
        source appearing mid-run would give two callers different answers.
        """
        config = submission_dirs.parseconfig("--sources", "submissions/*")
        first = resolve(config)

        monkeypatch.setattr(
            "pytest_sources._core.discover.discover",
            lambda *args: pytest.fail("discover called a second time"),
        )

        assert resolve(config) is first

    def test_resolve_returns_the_stashed_list_untouched(self, submission_dirs):
        config = submission_dirs.parseconfig("--sources", "submissions/*")
        config.stash[SOURCES] = []

        assert resolve(config) == []


class TestDiscover:
    """Expanding globs to source directories."""

    def test_expands_glob_to_directories(self, tree):
        assert relative(discover(["submissions/*"], tree), tree) == [
            "submissions/alice",
            "submissions/bob",
            "submissions/carol_alt",
            "submissions/zoe",
        ]

    def test_result_is_sorted_regardless_of_filesystem_order(self, tree):
        assert discover(["submissions/*"], tree) == sorted(discover(["submissions/*"], tree))

    def test_ignores_files_among_directory_matches(self, tree):
        assert tree / "submissions/README.md" not in discover(["submissions/*"], tree)

    def test_ignores_hidden_directories(self, tree):
        assert tree / "submissions/.git" not in discover(["submissions/*"], tree)

    def test_unions_multiple_patterns(self, tree):
        assert relative(discover(["submissions/*_alt", "other/*"], tree), tree) == [
            "other/alice",
            "submissions/carol_alt",
        ]

    def test_deduplicates_overlapping_patterns(self, tree):
        assert relative(discover(["submissions/alice", "submissions/a*"], tree), tree) == ["submissions/alice"]

    def test_deduplicates_symlinked_directories(self, tree):
        (tree / "submissions/link").symlink_to(tree / "submissions/alice")
        assert relative(discover(["submissions/*"], tree), tree) == [
            "submissions/alice",
            "submissions/bob",
            "submissions/carol_alt",
            "submissions/zoe",
        ]

    def test_accepts_absolute_pattern(self, tree):
        assert discover([str(tree / "submissions/*_alt")], tree) == [tree / "submissions/carol_alt"]

    def test_accepts_exact_path_without_magic(self, tree):
        assert discover(["submissions/bob"], tree) == [tree / "submissions/bob"]

    def test_accepts_pattern_escaping_the_root(self, tree):
        assert relative(discover(["../submissions/*_alt"], tree / "other"), tree) == ["submissions/carol_alt"]

    def test_normalises_dotdot_when_deduplicating(self, tree):
        assert discover(["submissions/alice", "submissions/../submissions/alice"], tree) == [
            tree / "submissions" / "alice"
        ]

    def test_recursive_pattern_includes_nested_directories(self, tree):
        assert tree / "submissions/alice/pkg" in discover(["submissions/**/"], tree)

    def test_no_patterns_yields_no_sources(self, tree):
        assert discover([], tree) == []

    def test_pattern_matching_nothing_is_a_usage_error(self, tree):
        with pytest.raises(pytest.UsageError, match=re.escape("matched nothing: 'nope/*'")):
            discover(["nope/*"], tree)

    def test_pattern_matching_only_files_is_a_usage_error(self, tree):
        with pytest.raises(pytest.UsageError, match="none of them directories"):
            discover(["submissions/README.md"], tree)

    def test_one_bad_pattern_fails_the_whole_expansion(self, tree):
        with pytest.raises(pytest.UsageError):
            discover(["submissions/*", "nope/*"], tree)


class TestUniverse:
    """Every source the run may touch, with and without the marker scan."""

    def test_with_the_scan_off_the_universe_is_the_declared_set(self, submission_dirs):
        config = submission_dirs.parseconfigure("--sources", "submissions/*", "--no-sources-scan")
        assert universe(config) == resolve(config)

    def test_the_scan_adds_marker_sources(self, submission_dirs):
        (submission_dirs.path / "refs" / "model").mkdir(parents=True)
        submission_dirs.makepyfile(
            """
            import pytest

            @pytest.mark.sources("refs/*")
            def test_x(source): ...
            """
        )

        config = submission_dirs.parseconfigure("--sources", "submissions/*")

        assert [source.id for source in universe(config)] == [
            "submissions/alice",
            "submissions/bob",
            "refs/model",
        ]

    def test_the_scan_deduplicates_declared_sources(self, submission_dirs):
        submission_dirs.makepyfile(
            """
            import pytest

            @pytest.mark.sources("submissions/alice")
            def test_x(source): ...
            """
        )

        config = submission_dirs.parseconfigure("--sources", "submissions/*")

        assert [source.id for source in universe(config)] == ["submissions/alice", "submissions/bob"]
