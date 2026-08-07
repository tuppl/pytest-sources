import re

import pytest

from pytest_sources._stash import SOURCES


@pytest.fixture
def submissions(pytester):
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    return pytester


def test_defaults_to_no_globs(pytester):
    assert pytester.parseconfig().getoption("sources") == []


def test_accepts_a_glob_verbatim(pytester):
    config = pytester.parseconfig("--sources", "submissions/*")
    assert config.getoption("sources") == ["submissions/*"]


def test_is_repeatable(pytester):
    config = pytester.parseconfig("--sources", "submissions/*", "--sources", "other/*")
    assert config.getoption("sources") == ["submissions/*", "other/*"]


def test_reads_globs_from_ini(pytester):
    pytester.makeini("[pytest]\nsources = submissions/* other/*\n")
    assert list(pytester.parseconfig().getini("sources")) == ["submissions/*", "other/*"]


def test_appears_in_help_under_its_own_group(pytester):
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(["sources:", "*--sources=GLOB*"])


def test_configure_stashes_discovered_directories(submissions):
    config = submissions.parseconfigure("--sources", "submissions/*")
    assert [source.path for source in config.stash[SOURCES]] == [
        submissions.path / "submissions" / "alice",
        submissions.path / "submissions" / "bob",
    ]


def test_configure_stashes_directories_from_ini(submissions):
    submissions.makeini("[pytest]\nsources = submissions/*\n")
    config = submissions.parseconfigure()
    assert [source.path for source in config.stash[SOURCES]] == [
        submissions.path / "submissions" / "alice",
        submissions.path / "submissions" / "bob",
    ]


def test_configure_stashes_root_relative_ids(submissions):
    config = submissions.parseconfigure("--sources", "submissions/*")
    assert [source.id for source in config.stash[SOURCES]] == [
        "submissions/alice",
        "submissions/bob",
    ]


def test_command_line_overrides_ini(submissions):
    submissions.makeini("[pytest]\nsources = submissions/*\n")
    config = submissions.parseconfigure("--sources", "submissions/alice")
    assert [source.path for source in config.stash[SOURCES]] == [submissions.path / "submissions" / "alice"]


def test_nothing_is_stashed_without_sources(submissions):
    assert SOURCES not in submissions.parseconfigure().stash


def test_glob_matching_nothing_is_a_usage_error(submissions):
    with pytest.raises(pytest.UsageError, match=re.escape("matched nothing: 'nope/*'")):
        submissions.parseconfigure("--sources", "nope/*")


def test_markers_are_registered(pytester):
    result = pytester.runpytest("--markers")
    result.stdout.fnmatch_lines(["@pytest.mark.sources*", "@pytest.mark.no_sources*"])
