import pytest


@pytest.fixture
def mixed(pytester):
    """Two sources whose results differ, so the columns cannot be confused."""
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    (pytester.path / "submissions" / "alice" / "solution.py").write_text("VALUE = 1\n")
    (pytester.path / "submissions" / "bob" / "solution.py").write_text("VALUE = 2\n")
    pytester.makepyfile(
        """
        import pytest

        def test_value(source):
            assert source.import_module("solution").VALUE == 1

        def test_always(source): ...

        @pytest.mark.skip(reason="not ready")
        def test_skipped(source): ...
        """
    )
    return pytester


@pytest.fixture
def parametrised_ahead(pytester):
    """Two sources under a plugin whose generate hook beats ours to the id.

    A conftest is registered after the entry point plugins, so its tryfirst
    pytest_generate_tests runs first and its parameter leads the bracket.
    """
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    pytester.makeconftest(
        """
        import pytest

        @pytest.fixture(scope="session")
        def axis(request):
            return request.param

        @pytest.hookimpl(tryfirst=True)
        def pytest_generate_tests(metafunc):
            if "axis" in metafunc.fixturenames:
                metafunc.parametrize("axis", ["w1"], indirect=True, scope="session")
        """
    )
    pytester.makepyfile(
        """
        def test_leading(axis, source): ...

        def test_plain(source): ...
        """
    )
    return pytester


def section(result):
    """The lines between the sources separator and whatever follows it."""
    lines = result.outlines
    start = next(i for i, line in enumerate(lines) if line.startswith("=") and " sources " in line)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("="):
            break
        body.append(line)
    return body


def grid(result):
    """The grid body, keyed by row label, header and legend removed."""
    body = section(result)[1:-1]
    return {line.split()[0]: line.split()[1:] for line in body}


def rows(result):
    """The counts body, keyed by source: passed, failed, error, skipped."""
    return {
        line.split()[0]: line.split()[1:5]
        for line in section(result)[1:]  # drop the header
    }


class TestCounts:
    """The default view, one row of totals per source."""

    def test_reports_a_row_for_each_source(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0")

        assert rows(result) == {
            "submissions/alice": ["2", "0", "0", "1"],
            "submissions/bob": ["1", "1", "0", "1"],
        }

    def test_each_row_ends_with_a_duration(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0")

        durations = [line.split()[-1] for line in result.outlines if line.startswith("submissions/")]
        assert durations and all(value.endswith("s") for value in durations)

    def test_a_source_with_no_tests_still_gets_a_row(self, mixed):
        """A source whose tests were all deselected, or whose worker died, reads zero."""
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "-k", "alice")

        assert rows(result)["submissions/bob"] == ["0", "0", "0", "0"]

    def test_the_totals_are_the_same_under_xdist(self, mixed):
        """Reports reach the controller either way, so distribution cannot change them."""
        serial = rows(mixed.runpytest("--sources", "submissions/*", "-n", "0"))
        distributed = rows(mixed.runpytest("--sources", "submissions/*", "-n", "2"))

        assert serial == distributed


class TestGrids:
    """A cell per source and test, either way round."""

    def test_sources_grid_puts_a_source_on_each_row(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

        assert grid(result) == {
            "submissions/alice": [".", "s", "."],
            "submissions/bob": [".", "s", "F"],
        }

    def test_tests_grid_is_the_transpose(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=tests")

        rows = grid(result)
        assert [cells[0] for cells in rows.values()] == [".", "s", "."]
        assert [cells[1] for cells in rows.values()] == [".", "s", "F"]

    def test_a_grid_explains_its_characters(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

        result.stdout.fnmatch_lines(["*. passed*F failed*E error*s skipped*- not run*"])

    def test_a_test_missing_from_a_source_reads_as_not_run(self, pytester):
        """A source whose worker died mid-item leaves gaps rather than false passes."""
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.sources("submissions/alice")
            def test_only_alice(source): ...

            def test_both(source): ...
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

        assert grid(result)["submissions/bob"] == [".", "-"]

    def test_the_grid_marks_xfail_and_xpass_as_pytest_does(self, pytester):
        (pytester.path / "submissions" / "alice").mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.xfail(reason="known")
            def test_expected_failure(source):
                assert False

            @pytest.mark.xfail(reason="known")
            def test_unexpected_pass(source):
                assert True
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

        assert grid(result)["submissions/alice"] == ["x", "X"]

    def test_a_grouped_test_is_labelled_without_its_group(self, pytester):
        """xdist appends "@group" to the nodeid, which the label must not carry."""
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.xdist_group("db")
            def test_grouped(source): ...
            """
        )

        result = pytester.runpytest(
            "--sources", "submissions/*", "--dist", "loadgroup", "-n", "2", "--sources-summary=sources"
        )

        assert section(result)[0].split()[1:] == ["test_grouped"]

    def test_sources_sharing_a_basename_keep_their_full_heading(self, pytester):
        """Shortening headings to the basename would merge these two columns."""
        for parent in ("submissions", "other"):
            (pytester.path / parent / "alice").mkdir(parents=True)
        pytester.makepyfile("def test_x(source): ...")

        result = pytester.runpytest(
            "--sources", "submissions/*", "--sources", "other/*", "-n", "0", "--sources-summary=tests"
        )

        assert section(result)[0].split()[1:] == ["other/alice", "submissions/alice"]


class TestForeignOutcomes:
    def test_a_foreign_outcome_is_left_out_of_the_tally(self, pytester):
        (pytester.path / "submissions" / "alice").mkdir(parents=True)
        pytester.makeconftest(
            """
            import pytest

            @pytest.hookimpl(wrapper=True)
            def pytest_runtest_makereport(item, call):
                report = yield
                if report.when == "call" and item.originalname == "test_retried":
                    report.outcome = "rerun"
                return report

            def pytest_report_teststatus(report, config):
                if report.outcome == "rerun":
                    return "rerun", "R", "RERUN"
            """
        )
        pytester.makepyfile(
            """
            def test_ok(source): ...
            def test_retried(source): ...
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")

        assert "INTERNALERROR" not in result.stdout.str()
        assert rows(result)["submissions/alice"] == ["1", "0", "0", "0"]


class TestOutcomes:
    """Folding a test's three phase reports into one result."""

    def test_counts_setup_failures_as_errors(self, pytester):
        (pytester.path / "submissions" / "alice").mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.fixture
            def broken():
                raise RuntimeError("boom")

            def test_x(source, broken): ...
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")

        assert rows(result)["submissions/alice"] == ["0", "0", "1", "0"]

    def test_xfail_and_xpass_are_counted_apart_from_pass_and_skip(self, pytester):
        """An xpass means the source did better than the test expected, which a
        plain "passed" would hide."""
        (pytester.path / "submissions" / "alice").mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.xfail(reason="known")
            def test_expected_failure(source):
                assert False

            @pytest.mark.xfail(reason="known")
            def test_unexpected_pass(source):
                assert True
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0")

        # passed failed error skipped xfailed xpassed
        assert rows(result)["submissions/alice"] == ["0", "0", "0", "0"]
        assert section(result)[0].split()[1:] == [
            "passed",
            "failed",
            "error",
            "skipped",
            "xfailed",
            "xpassed",
            "time",
        ]


class TestSummaryOption:
    """Choosing the view, or none at all."""

    def test_the_table_is_absent_without_sources(self, pytester):
        pytester.makepyfile("def test_x(): ...")

        result = pytester.runpytest()

        assert "sources" not in "".join(line for line in result.outlines if line.startswith("="))

    def test_none_prints_no_summary(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=none")

        assert not any("= sources =" in line for line in result.outlines)

    def test_an_unknown_summary_style_is_rejected(self, pytester):
        result = pytester.runpytest("--sources-summary=matrix")

        assert result.ret != 0
        result.stderr.fnmatch_lines(["*invalid choice*"])


class TestParametersAheadOfTheSource:
    """Another plugin's parameters may lead the id, and the source still counts."""

    def test_every_test_is_attributed_to_its_source(self, parametrised_ahead):
        result = parametrised_ahead.runpytest("--sources", "submissions/*", "-n", "0")

        assert rows(result) == {
            "submissions/alice": ["2", "0", "0", "0"],
            "submissions/bob": ["2", "0", "0", "0"],
        }

    def test_the_table_totals_agree_with_the_run(self, parametrised_ahead):
        """The counts used to add up to less than the run reported."""
        result = parametrised_ahead.runpytest("--sources", "submissions/*", "-n", "0")

        result.assert_outcomes(passed=4)
        assert sum(int(count) for counts in rows(result).values() for count in counts) == 4


class TestForeignItems:
    """Items another collector creates, one artifact per source.

    The plugin never parametrised them, so no token in their nodeid names a
    source. The conftest declares the owner through pytest_sources_source_of,
    reading back the property it recorded at collection.
    """

    @pytest.fixture
    def checks(self, pytester):
        for name in ("good", "slow"):
            (pytester.path / "sources" / name).mkdir(parents=True)
            (pytester.path / "checks" / name).mkdir(parents=True)
            (pytester.path / "checks" / name / "a.check").write_text("x\n")
        pytester.makeconftest(
            """
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

            OWNERS = {}

            def pytest_collection_modifyitems(config, items):
                for item in items:
                    if isinstance(item, CheckItem):
                        item.user_properties.append(("source", f"sources/{item.path.parent.name}"))
                        OWNERS[item.nodeid] = dict(item.user_properties)["source"]

            @pytest.hookimpl(optionalhook=True)
            def pytest_sources_source_of(nodeid):
                return OWNERS.get(nodeid)
            """
        )
        pytester.makepyfile("def test_ok(source): ...")
        return pytester

    def test_a_failing_check_counts_against_its_source(self, checks):
        result = checks.runpytest("--sources", "sources/*", "-n", "0")

        result.assert_outcomes(passed=3, failed=1)
        assert rows(result) == {
            "sources/good": ["2", "0", "0", "0"],
            "sources/slow": ["1", "1", "0", "0"],
        }


class TestUnattributed:
    """Results no mechanism could place, so a gap never reads as a pass."""

    @pytest.fixture
    def unclaimed(self, pytester):
        """A per-source artifact whose collector declares no owner."""
        for name in ("good", "slow"):
            (pytester.path / "sources" / name).mkdir(parents=True)
            (pytester.path / "checks" / name).mkdir(parents=True)
            (pytester.path / "checks" / name / "a.check").write_text("x\n")
        pytester.makeconftest(
            """
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
        )
        pytester.makepyfile("def test_ok(source): ...")
        return pytester

    def test_results_nothing_claims_are_totalled_in_their_own_row(self, unclaimed):
        result = unclaimed.runpytest("--sources", "sources/*", "-n", "0")

        assert rows(result) == {
            "sources/good": ["1", "0", "0", "0"],
            "sources/slow": ["1", "0", "0", "0"],
            "unattributed": ["1", "1", "0", "0"],
        }

    def test_the_row_is_there_under_xdist_too(self, unclaimed):
        """No worker could attribute them either, so the reports arrive bare."""
        result = unclaimed.runpytest("--sources", "sources/*", "-n", "2")

        assert rows(result)["unattributed"] == ["1", "1", "0", "0"]

    def test_the_row_ends_with_a_duration(self, unclaimed):
        result = unclaimed.runpytest("--sources", "sources/*", "-n", "0")

        line = next(line for line in result.outlines if line.startswith("unattributed"))
        assert line.split()[-1].endswith("s")

    def test_no_row_appears_when_every_result_is_placed(self, mixed):
        result = mixed.runpytest("--sources", "submissions/*", "-n", "0")

        assert "unattributed" not in rows(result)


class TestCombinedParametrize:
    """A harness parametrising source and case together, in one call.

    pytest joins the values of a single parametrize call with "-", not the
    sources delimiter, so the source cannot be read back out of the id.
    """

    @pytest.fixture
    def combined(self, pytester):
        for name in ("good", "slow"):
            (pytester.path / "sources" / name).mkdir(parents=True)
        pytester.makeconftest(
            """
            def pytest_generate_tests(metafunc):
                if "case" in metafunc.fixturenames:
                    pairs = [(s, c) for s in ("sources/good", "sources/slow") for c in ("alpha", "beta")]
                    metafunc.parametrize("source,case", pairs)
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.no_sources
            def test_combined(source, case):
                assert not (source == "sources/slow" and case == "beta")
            """
        )
        return pytester

    @pytest.mark.parametrize("workers", ["0", "2"])
    def test_the_failure_counts_against_its_source(self, combined, workers):
        """Under workers the controller never collects, so the attribution has to
        reach it on the report rather than from a map of its own."""
        result = combined.runpytest("--sources", "sources/*", "-n", workers)

        result.assert_outcomes(passed=3, failed=1)
        assert rows(result) == {
            "sources/good": ["2", "0", "0", "0"],
            "sources/slow": ["1", "1", "0", "0"],
        }
