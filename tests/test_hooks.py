import pytest

COLLECTOR = """
    import pytest

    def pytest_collect_file(parent, file_path):
        if file_path.suffix == ".check":
            return CheckFile.from_parent(parent, path=file_path)

    class CheckFile(pytest.File):
        def collect(self):
            yield CheckItem.from_parent(self, name="verify")

    class CheckItem(pytest.Item):
        def runtest(self):
            if self.path.parent.name == "slow":
                raise AssertionError("check failed")

        def repr_failure(self, excinfo):
            return str(excinfo.value)
"""

CLAIM = """
    @pytest.hookimpl(optionalhook=True)
    def pytest_sources_source_of(nodeid):
        path = nodeid.split("::")[0]
        if path.endswith(".check"):
            return f"sources/{path.rsplit('/', 2)[-2]}"
        return None
"""

GHOST = """
    @pytest.hookimpl(optionalhook=True)
    def pytest_sources_source_of(nodeid):
        return "sources/ghost"
"""

EVERYTHING = """
    @pytest.hookimpl(optionalhook=True)
    def pytest_sources_source_of(nodeid):
        return "sources/slow"
"""


def conftest(claim):
    """The collector making one check item per source, plus the given hook."""
    return COLLECTOR + claim


def rows(result):
    """The counts body of the sources section, keyed by label."""
    lines = result.outlines
    start = next(i for i, line in enumerate(lines) if line.startswith("=") and " sources " in line)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("="):
            break
        body.append(line)
    return {line.split()[0]: line.split()[1:5] for line in body[1:]}


def worker_items(result):
    """Map each worker id to the nodeids it reported an outcome for."""
    items: dict[str, set[str]] = {}
    for line in result.outlines:
        if "[gw" not in line:
            continue
        for outcome in ("PASSED", "FAILED"):
            if outcome in line:
                worker = line[line.index("[gw") + 1 : line.index("]")]
                items.setdefault(worker, set()).add(line.rsplit(f"{outcome} ", 1)[-1].strip())
    return items


def names(nodeids):
    """Which of the two source names each nodeid mentions."""
    return {"slow" if "slow" in nodeid else "good" for nodeid in nodeids}


@pytest.fixture
def checks(pytester):
    """Two sources whose per-source artifact is collected by the rootdir conftest."""
    for name in ("good", "slow"):
        (pytester.path / "sources" / name).mkdir(parents=True)
        (pytester.path / "checks" / name).mkdir(parents=True)
        (pytester.path / "checks" / name / "a.check").write_text("x\n")
    pytester.makepyfile("def test_ok(source): ...")
    return pytester


class TestDeclaringASource:
    """A harness claiming the items pytest-sources never fanned out."""

    def test_a_claimed_failure_counts_against_its_source(self, checks):
        checks.makeconftest(conftest(CLAIM))

        result = checks.runpytest("--sources", "sources/*", "-n", "0")

        assert rows(result) == {
            "sources/good": ["2", "0", "0", "0"],
            "sources/slow": ["1", "1", "0", "0"],
        }

    def test_a_claimed_failure_counts_against_its_source_under_xdist(self, checks):
        """The controller prints the table and never collected, so the hook answers there too."""
        checks.makeconftest(conftest(CLAIM))

        result = checks.runpytest("--sources", "sources/*", "-n", "2")

        result.assert_outcomes(passed=3, failed=1)
        assert rows(result) == {
            "sources/good": ["2", "0", "0", "0"],
            "sources/slow": ["1", "1", "0", "0"],
        }

    def test_a_claimed_failure_spends_its_sources_budget_under_xdist(self, checks):
        checks.makeconftest(conftest(CLAIM))

        result = checks.runpytest("--sources", "sources/*", "-n", "2", "--sources-maxfail=1")

        result.assert_outcomes(passed=2, failed=1, skipped=1)

    def test_a_claimed_item_runs_in_its_sources_process(self, checks):
        """The scheduler reads the hook as well, so a check rides with its own source."""
        checks.makeconftest(conftest(CLAIM))

        result = checks.runpytest("--sources", "sources/*", "-n", "2", "-v")

        assignments = worker_items(result)
        assert len(assignments) == 2
        assert all(len(names(nodeids)) == 1 for nodeids in assignments.values())
        assert all(len(nodeids) == 2 for nodeids in assignments.values())

    def test_an_unclaimed_item_runs_apart_from_its_source(self, checks):
        """Without the hook every unfanned item shares one work item, sources mixed."""
        checks.makeconftest(conftest(""))

        result = checks.runpytest("--sources", "sources/*", "-n", "2", "-v")

        assignments = worker_items(result)
        assert {"good", "slow"} in [names(nodeids) for nodeids in assignments.values()]

    def test_a_source_outside_the_run_is_ignored(self, checks):
        """A claim naming no known source attributes nothing, as an unreadable id does."""
        checks.makeconftest(conftest(GHOST))

        result = checks.runpytest("--sources", "sources/*", "-n", "0")

        result.assert_outcomes(passed=3, failed=1)
        assert rows(result) == {
            "sources/good": ["1", "0", "0", "0"],
            "sources/slow": ["1", "0", "0", "0"],
            "unattributed": ["1", "1", "0", "0"],
        }

    def test_the_hook_cannot_move_a_test_the_plugin_fanned_out(self, checks):
        """The id parse is authoritative, so a claim over every nodeid changes nothing."""
        checks.makeconftest(conftest(EVERYTHING))

        result = checks.runpytest("--sources", "sources/*", "-n", "0", "-k", "test_ok")

        assert rows(result) == {
            "sources/good": ["1", "0", "0", "0"],
            "sources/slow": ["1", "0", "0", "0"],
        }
