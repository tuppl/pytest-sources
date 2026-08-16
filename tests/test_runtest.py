import sys

import pytest

from pytest_sources._core import source as source_module


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
def submissions(pytester):
    for name, value in (("alice", 1), ("bob", 2)):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text(f"VALUE = {value}\n")
    return pytester


class TestSourceActivation:
    def test_a_test_that_never_requests_source_can_import_it(self, submissions):
        submissions.makepyfile(
            """
            def test_value():
                import solution
                assert solution.VALUE in (1, 2)
            """
        )
        result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
        result.assert_outcomes(passed=2)

    def test_it_still_works_when_selected_on_its_own(self, submissions):
        """Selection must not decide it: a sibling requesting source activates on its behalf."""
        submissions.makepyfile(
            """
            def test_requests_source(source):
                import solution

            def test_does_not():
                import solution
            """
        )
        result = submissions.runpytest("--sources", "submissions/*", "-n", "0", "-k", "does_not")
        result.assert_outcomes(passed=2, deselected=2)

    def test_a_fixture_may_import_the_source(self, submissions):
        """The hook is tryfirst, so the source is there before fixtures run."""
        submissions.makepyfile(
            """
            import pytest

            @pytest.fixture
            def value():
                import solution
                return solution.VALUE

            def test_value(value):
                assert value in (1, 2)
            """
        )
        result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
        result.assert_outcomes(passed=2)

    def test_an_unfanned_test_does_not_get_a_source(self, submissions):
        submissions.makepyfile(
            """
            import pytest

            @pytest.mark.no_sources
            def test_x():
                with pytest.raises(ModuleNotFoundError):
                    import solution
            """
        )
        result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
        result.assert_outcomes(passed=1)

    def test_an_unfanned_test_does_not_inherit_the_source_before_it(self, submissions):
        """A source stays active across its group, so an unfanned test running
        after a fanned one would otherwise import whatever was left behind."""
        submissions.makepyfile(
            """
            import pytest

            def test_fanned(source):
                import solution

            @pytest.mark.no_sources
            def test_unfanned():
                with pytest.raises(ModuleNotFoundError):
                    import solution
            """
        )
        result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
        result.assert_outcomes(passed=3)
