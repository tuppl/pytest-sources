from pathlib import Path

import pytest

# 4 is more workers than there are groups, so some start with nothing to do.
WORKERS = ["0", "1", "2", "4", "auto"]


@pytest.fixture
def cwd_probe(pytester, tmp_path, monkeypatch):
    """Two sources whose tests record the working directory they ran in."""
    monkeypatch.setenv("CWDDIR", str(tmp_path))
    for name in ("alice", "bob"):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "data.txt").write_text(f"{name}\n")
    pytester.makepyfile(
        """
        import os, pathlib, pytest

        def record(label):
            pathlib.Path(os.environ["CWDDIR"], label).write_text(os.getcwd())

        def test_fanned(source):
            record(f"fanned-{source.name}")

        @pytest.mark.no_chdir
        def test_opted_out(source):
            record("opted-out")

        @pytest.mark.no_sources
        def test_unfanned():
            record("unfanned")
        """
    )
    return pytester, tmp_path


class TestAutomaticMove:
    """Every fanned test runs inside the source it is testing."""

    @pytest.mark.parametrize("workers", WORKERS)
    def test_a_fanned_test_runs_inside_its_source(self, cwd_probe, workers):
        pytester, recorded = cwd_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", workers)
        result.assert_outcomes(passed=5)

        for name in ("alice", "bob"):
            assert (recorded / f"fanned-{name}").read_text() == str(pytester.path / "submissions" / name)

    @pytest.mark.parametrize("workers", WORKERS)
    def test_an_unfanned_test_keeps_the_invocation_directory(self, cwd_probe, workers):
        pytester, recorded = cwd_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", workers)
        result.assert_outcomes(passed=5)

        assert (recorded / "unfanned").read_text() == str(pytester.path)

    @pytest.mark.parametrize("workers", WORKERS)
    def test_a_source_reading_at_import_finds_its_own_file(self, pytester, workers):
        """The case manual chdir cannot fix, because the first import wins."""
        for name in ("alice", "bob"):
            directory = pytester.path / "submissions" / name
            directory.mkdir(parents=True)
            (directory / "data.txt").write_text(f"{name}\n")
            (directory / "solution.py").write_text(
                'import pathlib\nAT_IMPORT = pathlib.Path("data.txt").read_text().strip()\n'
            )
        pytester.makepyfile(
            """
            def test_first(source):
                assert source.import_module("solution").AT_IMPORT == source.name

            def test_second(source):
                assert source.import_module("solution").AT_IMPORT == source.name
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", workers)

        result.assert_outcomes(passed=4)

    def test_how_far_the_move_reaches(self, cwd_probe):
        """Function-scoped fixtures move with the test; wider ones do not.

        Autouse fixtures set up before other function-scoped ones, so a fixture the
        test requests runs inside the source. A module-scoped fixture is already set
        up by then, so it sees the directory pytest was started in.
        """
        pytester, recorded = cwd_probe
        pytester.makepyfile(
            """
            import os, pathlib, pytest

            @pytest.fixture
            def function_scoped():
                return os.getcwd()

            @pytest.fixture(scope="module")
            def module_scoped():
                return os.getcwd()

            def test_reach(source, function_scoped, module_scoped):
                pathlib.Path(os.environ["CWDDIR"], "reach").write_text(
                    f"{function_scoped}|{module_scoped}|{os.getcwd()}"
                )
            """
        )

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=2)

        function, module, body = (recorded / "reach").read_text().split("|")
        assert function == body == str(pytester.path / "submissions" / "bob")
        assert module == str(pytester.path)


class TestOptingOut:
    """Keeping the directory pytest was started in."""

    @pytest.mark.parametrize("workers", WORKERS)
    def test_no_chdir_keeps_the_invocation_directory(self, cwd_probe, workers):
        pytester, recorded = cwd_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", workers)
        result.assert_outcomes(passed=5)

        assert (recorded / "opted-out").read_text() == str(pytester.path)

    def test_no_chdir_applies_to_a_whole_module(self, cwd_probe):
        pytester, recorded = cwd_probe
        pytester.makepyfile(
            """
            import os, pathlib, pytest

            pytestmark = pytest.mark.no_chdir

            def test_fanned(source):
                pathlib.Path(os.environ["CWDDIR"], f"fanned-{source.name}").write_text(os.getcwd())
            """
        )

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=2)

        assert (recorded / "fanned-alice").read_text() == str(pytester.path)

    def test_no_chdir_still_allows_moving_in_by_hand(self, pytester):
        """Opting out of the automatic move does not take the manual one away."""
        directory = pytester.path / "submissions" / "alice"
        directory.mkdir(parents=True)
        (directory / "data.txt").write_text("hello\n")
        (directory / "solution.py").write_text('def read():\n    return open("data.txt").read().strip()\n')
        pytester.makepyfile(
            """
            import os, pathlib, pytest

            @pytest.mark.no_chdir
            def test_x(source):
                outside = pathlib.Path.cwd()
                solution = source.import_module("solution")
                with source.chdir():
                    assert solution.read() == "hello"
                assert pathlib.Path.cwd() == outside
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")

        result.assert_outcomes(passed=1)


class TestRestoration:
    """Putting the directory back, however the test ends."""

    def test_the_run_leaves_the_calling_directory_alone(self, cwd_probe):
        """pytester runs in-process, so a leaked chdir would follow us out."""
        pytester, _ = cwd_probe
        before = Path.cwd()

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=5)

        assert Path.cwd() == before

    def test_a_failing_test_does_not_leave_the_directory_moved(self, pytester):
        pytester.makepyfile("def test_x(source): assert False")
        (pytester.path / "submissions" / "alice").mkdir(parents=True)
        before = Path.cwd()

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(failed=1)

        assert Path.cwd() == before
