import os
import sys
from pathlib import Path

import pytest

from pytest_sources import source as source_module
from pytest_sources.source import Source, SourceImportError, make_sources


@pytest.fixture(autouse=True)
def isolate_imports():
    original_path = list(sys.path)
    original_modules = set(sys.modules)
    yield
    source_module._active = None
    sys.path[:] = original_path
    for name in set(sys.modules) - original_modules:
        del sys.modules[name]


@pytest.fixture
def root(tmp_path):
    return tmp_path.resolve()


@pytest.fixture
def sources(root):
    for name, value in (("alice", 1), ("bob", 2)):
        directory = root / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text(f"VALUE = {value}\n")
    return make_sources([root / "submissions" / "alice", root / "submissions" / "bob"], root)


@pytest.fixture
def alice(sources):
    return sources[0]


@pytest.fixture
def bob(sources):
    return sources[1]


class TestIdentity:
    """What a Source is called and how it compares."""

    def test_id_is_root_relative(self, alice):
        assert alice.id == "submissions/alice"

    def test_id_of_source_outside_the_root(self, root, alice):
        (outside,) = make_sources([alice.path], root / "grading")
        assert outside.id == "../submissions/alice"

    def test_name_is_the_basename(self, alice):
        assert alice.name == "alice"

    def test_str_is_the_id(self, alice):
        assert str(alice) == "submissions/alice"

    def test_is_path_like(self, alice):
        assert os.fspath(alice) == str(alice.path)

    def test_division_yields_a_path_inside_the_source(self, alice):
        assert (alice / "solution.py").read_text() == "VALUE = 1\n"

    def test_sources_compare_by_value(self, alice):
        assert Source(path=alice.path, id=alice.id) == alice


class TestChdir:
    """Moving the working directory into a source by hand."""

    def test_chdir_moves_into_the_source(self, alice):
        with alice.chdir():
            assert Path.cwd() == alice.path

    def test_chdir_restores_the_previous_directory(self, alice):
        before = Path.cwd()

        with alice.chdir():
            pass

        assert Path.cwd() == before

    def test_chdir_restores_even_when_the_block_raises(self, alice):
        before = Path.cwd()

        with pytest.raises(RuntimeError), alice.chdir():
            raise RuntimeError("boom")

        assert Path.cwd() == before

    def test_chdir_nests(self, alice, bob):
        with alice.chdir():
            with bob.chdir():
                assert Path.cwd() == bob.path
            assert Path.cwd() == alice.path

    def test_a_relative_path_resolves_inside_the_source(self, alice):
        """The reason the method exists: open("data.txt") in a source finds its own."""
        (alice / "data.txt").write_text("hello\n")

        with alice.chdir():
            assert Path("data.txt").read_text() == "hello\n"

    def test_a_relative_path_misses_the_source_without_it(self, alice):
        (alice / "only-in-the-source.txt").write_text("hello\n")

        assert not Path("only-in-the-source.txt").exists()
        with alice.chdir():
            assert Path("only-in-the-source.txt").exists()


class TestActivation:
    """Putting a source on sys.path and taking it off again."""

    def test_activate_puts_the_source_first_on_sys_path(self, alice):
        alice.activate()
        assert sys.path[0] == str(alice.path)

    def test_activate_is_idempotent(self, alice):
        alice.activate()
        alice.activate()
        assert sys.path.count(str(alice.path)) == 1

    def test_deactivate_removes_the_source_from_sys_path(self, alice):
        alice.activate()
        alice.deactivate()
        assert str(alice.path) not in sys.path

    def test_activating_another_source_deactivates_the_first(self, alice, bob):
        alice.activate()
        bob.activate()
        assert str(alice.path) not in sys.path
        assert sys.path[0] == str(bob.path)

    def test_deactivate_evicts_the_sources_modules(self, alice):
        alice.import_module("solution")
        alice.deactivate()
        assert "solution" not in sys.modules

    def test_deactivate_leaves_unrelated_modules_alone(self, alice):
        alice.import_module("solution")
        alice.deactivate()
        assert "pytest" in sys.modules


class TestImportModule:
    """Importing a source's own code."""

    def test_import_module_returns_the_sources_own_module(self, alice):
        assert alice.import_module("solution").VALUE == 1

    def test_switching_sources_returns_the_other_implementation(self, alice, bob):
        assert alice.import_module("solution").VALUE == 1
        assert bob.import_module("solution").VALUE == 2

    def test_missing_module_raises_source_import_error(self, alice):
        with pytest.raises(SourceImportError, match="submissions/alice has no module 'nope'"):
            alice.import_module("nope")

    def test_import_error_from_inside_the_source_propagates(self, alice):
        (alice / "broken.py").write_text("import definitely_not_installed_xyz\n")
        with pytest.raises(ModuleNotFoundError):
            alice.import_module("broken")
