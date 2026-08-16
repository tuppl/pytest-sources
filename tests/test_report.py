import pytest


@pytest.fixture
def submissions(pytester):
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    pytester.makepyfile("def test_x(source): pass")
    return pytester


class TestSharedProcessHeader:
    """Saying up front when sources share one process."""

    def test_a_bare_run_says_sources_share_a_process(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*")

        result.stdout.fnmatch_lines(["sources: 2 in one shared process*-n auto*"])

    def test_an_explicit_n_0_says_it_too(self, submissions):
        """-n 0 is deliberate, but the line is information rather than a warning."""
        result = submissions.runpytest("--sources", "submissions/*", "-n", "0")

        result.stdout.fnmatch_lines(["sources: 2 in one shared process*"])

    def test_a_run_without_sources_stays_quiet(self, pytester):
        pytester.makepyfile("def test_x(): pass")

        result = pytester.runpytest()

        result.stdout.no_fnmatch_line("*sources:*")


class TestDistributedHeader:
    """Counting sources, workers and work items for a distributed run."""

    def test_a_worker_per_source_is_one_work_item_each(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*", "-n", "2")

        result.stdout.fnmatch_lines(["sources: 2, workers: 2, work items: 2"])

    def test_fewer_workers_than_sources_is_still_one_each(self, submissions):
        (submissions.path / "submissions" / "carol").mkdir()

        result = submissions.runpytest("--sources", "submissions/*", "-n", "2")

        result.stdout.fnmatch_lines(["sources: 3, workers: 2, work items: 3"])

    def test_spare_workers_split_sources_into_more_items(self, submissions):
        """An upper bound: chunking caps at each source's test count, which is
        unknown until collection."""
        result = submissions.runpytest("--sources", "submissions/*", "-n", "4")

        result.stdout.fnmatch_lines(["sources: 2, workers: 4, work items: up to 4"])

    def test_n_auto_reports_the_resolved_count(self, submissions):
        """xdist turns auto into a number before the header is printed."""
        result = submissions.runpytest("--sources", "submissions/*", "-n", "auto")

        result.stdout.fnmatch_lines(["sources: 2, workers: 2, work items: 2"])

    def test_maxfail_keeps_one_item_per_source(self, submissions):
        """Splitting a source would split its failure budget."""
        result = submissions.runpytest("--sources", "submissions/*", "-n", "4", "--sources-maxfail=1")

        result.stdout.fnmatch_lines(["sources: 2, workers: 4, work items: 2"])

    def test_a_grouping_mode_defers_to_collection(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*", "-n", "2", "--dist", "loadfile")

        result.stdout.fnmatch_lines(["sources: 2, workers: 2, work items: decided by --dist loadfile"])
