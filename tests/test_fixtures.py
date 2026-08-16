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


@pytest.fixture
def read_probe(pytester, tmp_path, monkeypatch):
    """A data.txt in each source and another beside the test suite, all different.

    The name is deliberately the same in both places, so what a relative open
    returns names where it looked rather than what it happened to find.
    """
    monkeypatch.setenv("CWDDIR", str(tmp_path))
    for name in ("alice", "bob"):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "data.txt").write_text(f"{name}\n")
        (directory / "solution.py").write_text('def read():\n    return open("data.txt").read().strip()\n')
    (pytester.path / "data.txt").write_text("suite\n")
    pytester.makepyfile(
        """
        import os, pathlib, pytest

        def record(label, value):
            pathlib.Path(os.environ["CWDDIR"], label).write_text(value)

        def test_body_reads(source):
            record(f"body-{source.name}", open("data.txt").read().strip())

        def test_source_reads(source):
            record(f"source-{source.name}", source.import_module("solution").read())

        @pytest.mark.no_chdir
        def test_opted_out_reads(source):
            record(f"opted-out-{source.name}", open("data.txt").read().strip())

        @pytest.mark.no_sources
        def test_unfanned_reads():
            record("unfanned", open("data.txt").read().strip())
        """
    )
    return pytester, tmp_path


class TestAutomaticMove:
    """Every fanned test runs inside the source it is testing."""

    def test_a_fanned_test_runs_inside_its_source(self, cwd_probe):
        pytester, recorded = cwd_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")
        result.assert_outcomes(passed=5)

        for name in ("alice", "bob"):
            assert (recorded / f"fanned-{name}").read_text() == str(pytester.path / "submissions" / name)

    def test_an_unfanned_test_keeps_the_invocation_directory(self, cwd_probe):
        pytester, recorded = cwd_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")
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

    def test_no_chdir_keeps_the_invocation_directory(self, cwd_probe):
        pytester, recorded = cwd_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")
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


class TestRelativePaths:
    """Where a relative open lands, on both sides of the test boundary.

    The rest of this file asserts on the working directory itself. These assert
    on what opening a file through it actually returns, which is the thing the
    working directory exists to decide.
    """

    @pytest.mark.parametrize("workers", WORKERS)
    def test_the_test_body_reads_the_sources_copy(self, read_probe, workers):
        pytester, recorded = read_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", workers)
        result.assert_outcomes(passed=7)

        for name in ("alice", "bob"):
            assert (recorded / f"body-{name}").read_text() == name

    @pytest.mark.parametrize("workers", WORKERS)
    def test_a_source_function_reads_its_own_copy(self, read_probe, workers):
        """Call time in a default run, the case that needs no source.chdir().

        The import-time case is covered above; this is the same file read from a
        function the test calls, where a manual chdir would have been an option.
        """
        pytester, recorded = read_probe

        result = pytester.runpytest("--sources", "submissions/*", "-n", workers)
        result.assert_outcomes(passed=7)

        for name in ("alice", "bob"):
            assert (recorded / f"source-{name}").read_text() == name

    def test_no_chdir_sends_the_open_back_to_the_suite(self, read_probe):
        """The documented cost: a relative path in your own tests moves too."""
        pytester, recorded = read_probe

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=7)

        for name in ("alice", "bob"):
            assert (recorded / f"opted-out-{name}").read_text() == "suite"

    def test_an_unfanned_test_reads_the_suites_copy(self, read_probe):
        pytester, recorded = read_probe

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=7)

        assert (recorded / "unfanned").read_text() == "suite"

    def test_one_filename_gives_three_answers_in_a_single_run(self, read_probe):
        """Both files exist under the same name, so the directory is what decides."""
        pytester, recorded = read_probe

        pytester.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=7)

        assert {
            (recorded / "body-alice").read_text(),
            (recorded / "body-bob").read_text(),
            (recorded / "opted-out-alice").read_text(),
        } == {"alice", "bob", "suite"}


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


class TestSourceFixture:
    """The source fixture without any sources configured."""

    def test_requesting_source_without_any_sources_skips(self, pytester):
        pytester.makepyfile("def test_x(source): pass")
        result = pytester.runpytest("-rs")
        result.assert_outcomes(skipped=1)
        result.stdout.fnmatch_lines(["*no sources configured*"])
