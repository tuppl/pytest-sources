import pytest

from pytest_sources._dist import Dist, request_dist


class TestRequestedDist:
    """Recovering what the user asked --dist for, before xdist rewrites it."""

    def test_nothing_asked_for_reads_as_unset(self, pytester):
        assert request_dist(pytester.parseconfig()) is None

    @pytest.mark.parametrize("spelling", [("--dist", "no"), ("--dist=no",)])
    def test_an_explicit_no_is_not_the_default(self, pytester, spelling):
        """xdist defaults dist to "no", so option alone cannot tell these apart.

        Both spellings matter: only the argument scan can see an explicit "no",
        and it has to match the separated and joined forms separately.
        """
        assert request_dist(pytester.parseconfig(*spelling)) is Dist.NO

    @pytest.mark.parametrize("mode", ["loadfile", "loadscope", "loadgroup", "each", "worksteal"])
    def test_a_named_mode_is_returned(self, pytester, mode):
        assert request_dist(pytester.parseconfig(f"--dist={mode}")) is Dist(mode)

    def test_the_load_shortcut_is_recognised(self, pytester):
        assert request_dist(pytester.parseconfig("-d")) is Dist.LOAD

    def test_a_mode_set_in_addopts_is_seen(self, pytester):
        """addopts never reaches invocation_params, which holds the command line."""
        pytester.makeini(
            """
            [pytest]
            addopts = --dist no
            """
        )
        assert request_dist(pytester.parseconfig()) is Dist.NO

    def test_a_missing_dist_option_reads_as_unset(self, pytester):
        """--dist does not exist when xdist is disabled with -p no:xdist."""
        assert request_dist(pytester.parseconfig("-p", "no:xdist")) is None


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
