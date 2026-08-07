import re

import pytest

from pytest_sources._discover import discover


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


def relative(paths, root):
    return [str(p.relative_to(root)) for p in paths]


def test_expands_glob_to_directories(tree):
    assert relative(discover(["submissions/*"], tree), tree) == [
        "submissions/alice",
        "submissions/bob",
        "submissions/carol_alt",
        "submissions/zoe",
    ]


def test_result_is_sorted_regardless_of_filesystem_order(tree):
    assert discover(["submissions/*"], tree) == sorted(
        discover(["submissions/*"], tree)
    )


def test_ignores_files_among_directory_matches(tree):
    assert tree / "submissions/README.md" not in discover(["submissions/*"], tree)


def test_ignores_hidden_directories(tree):
    assert tree / "submissions/.git" not in discover(["submissions/*"], tree)


def test_unions_multiple_patterns(tree):
    assert relative(discover(["submissions/*_alt", "other/*"], tree), tree) == [
        "other/alice",
        "submissions/carol_alt",
    ]


def test_deduplicates_overlapping_patterns(tree):
    assert relative(discover(["submissions/alice", "submissions/a*"], tree), tree) == [
        "submissions/alice"
    ]


def test_deduplicates_symlinked_directories(tree):
    (tree / "submissions/link").symlink_to(tree / "submissions/alice")
    assert relative(discover(["submissions/*"], tree), tree) == [
        "submissions/alice",
        "submissions/bob",
        "submissions/carol_alt",
        "submissions/zoe",
    ]


def test_accepts_absolute_pattern(tree):
    assert discover([str(tree / "submissions/*_alt")], tree) == [
        tree / "submissions/carol_alt"
    ]


def test_accepts_exact_path_without_magic(tree):
    assert discover(["submissions/bob"], tree) == [tree / "submissions/bob"]


def test_accepts_pattern_escaping_the_root(tree):
    assert relative(discover(["../submissions/*_alt"], tree / "other"), tree) == [
        "submissions/carol_alt"
    ]


def test_normalises_dotdot_when_deduplicating(tree):
    assert discover(
        ["submissions/alice", "submissions/../submissions/alice"], tree
    ) == [tree / "submissions" / "alice"]


def test_recursive_pattern_includes_nested_directories(tree):
    assert tree / "submissions/alice/pkg" in discover(["submissions/**/"], tree)


def test_no_patterns_yields_no_sources(tree):
    assert discover([], tree) == []


def test_pattern_matching_nothing_is_a_usage_error(tree):
    with pytest.raises(pytest.UsageError, match=re.escape("matched nothing: 'nope/*'")):
        discover(["nope/*"], tree)


def test_pattern_matching_only_files_is_a_usage_error(tree):
    with pytest.raises(pytest.UsageError, match="none of them directories"):
        discover(["submissions/README.md"], tree)


def test_one_bad_pattern_fails_the_whole_expansion(tree):
    with pytest.raises(pytest.UsageError):
        discover(["submissions/*", "nope/*"], tree)
