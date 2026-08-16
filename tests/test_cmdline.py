import pytest


class TestDelimiterAtCmdline:
    """The delimiter is settled during pytest_cmdline_main, before anything reads it."""

    def test_the_scheduler_follows_the_chosen_character(self, pytester):
        """source_of splits on it, so a wrong delimiter misroutes every test."""
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1, 2])
            def test_x(source, n): ...
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "--sources-delimiter=@", "-n", "2", "-v")

        result.assert_outcomes(passed=4)

    def test_a_real_run_settles_it_before_the_sources_are_validated(self, pytester):
        """xdist asks for a worker count during pytest_cmdline_main, which
        validates the sources, all before any pytest_configure runs."""
        for name in ("alice+extra", "bob-2"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile("def test_x(source): ...")

        result = pytester.runpytest("--sources", "submissions/*", "--sources-delimiter=@")

        result.assert_outcomes(passed=2)


class TestDistMode:
    """Honouring an explicit --dist rather than overriding it."""

    def test_dist_no_starts_no_workers(self, submissions):
        """Distribution off means the calling process, not two workers.

        Implying -n auto used to reach xdist, which flips dist back to load as
        soon as a worker count is set.
        """
        result = submissions.runpytest("--sources", "submissions/*", "--dist", "no", "-v")

        result.assert_outcomes(passed=6)
        result.stdout.no_fnmatch_line("*created:*workers*")

    def test_an_explicit_worker_count_beats_dist_no(self, submissions):
        """xdist's own rule for the pair, left alone: a worker count wins.

        All --dist no asks of us is that we not imply one.
        """
        result = submissions.runpytest("--sources", "submissions/*", "--dist", "no", "-n", "2")

        result.assert_outcomes(passed=6)
        result.stdout.fnmatch_lines(["*created: 2/2 workers*"])

    @pytest.mark.parametrize("mode", ["each", "worksteal"])
    def test_a_mode_that_cannot_isolate_sources_is_refused(self, submissions, mode):
        result = submissions.runpytest("--sources", "submissions/*", "--dist", mode)

        assert result.ret == pytest.ExitCode.USAGE_ERROR
        result.stderr.fnmatch_lines([f"*--dist {mode} cannot give each source its own process*"])

    @pytest.mark.parametrize("mode", ["each", "worksteal"])
    def test_an_explicit_worker_count_does_not_skip_the_refusal(self, submissions, mode):
        """The check sits outside the "was -n given" branch, which it once did not."""
        result = submissions.runpytest("--sources", "submissions/*", "-n", "2", "--dist", mode)

        assert result.ret == pytest.ExitCode.USAGE_ERROR

    @pytest.mark.parametrize("mode", ["loadfile", "loadscope", "loadgroup"])
    def test_a_grouping_mode_is_refused_alongside_sources_maxfail(self, submissions, mode):
        """A grouping mode splits a source, and the budget is counted per process."""
        result = submissions.runpytest("--sources", "submissions/*", "--dist", mode, "--sources-maxfail=1")

        assert result.ret == pytest.ExitCode.USAGE_ERROR
        result.stderr.fnmatch_lines(["*--sources-maxfail counts failures per source*"])

    def test_sources_maxfail_is_unaffected_without_a_grouping_mode(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*", "--sources-maxfail=1")
        result.assert_outcomes(passed=6)

    def test_a_run_without_sources_is_left_to_xdist(self, pytester):
        """The refusals are about --sources, so plain xdist keeps every mode."""
        pytester.makepyfile("def test_one(): pass")
        result = pytester.runpytest("--dist", "worksteal", "-n", "1")
        result.assert_outcomes(passed=1)


class TestOptInDistribution:
    """Workers exist only when the user asks for them, like plain xdist."""

    def test_no_workers_are_implied_by_sources_alone(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*")

        result.assert_outcomes(passed=6)
        result.stdout.no_fnmatch_line("*created:*workers*")

    def test_a_bare_run_shares_one_process(self, pytester, tmp_path, monkeypatch):
        monkeypatch.setenv("PIDDIR", str(tmp_path))
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import os, pathlib

            def test_pid(source):
                pathlib.Path(os.environ["PIDDIR"], source.name).write_text(str(os.getpid()))
            """
        )

        result = pytester.runpytest("--sources", "submissions/*")

        result.assert_outcomes(passed=2)
        assert len({path.read_text() for path in tmp_path.iterdir()}) == 1
