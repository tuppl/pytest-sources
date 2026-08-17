import pytest

from pytest_sources._core.nodeid import DEFAULT


class TestSourcesOption:
    """Declaring --sources and the sources ini key."""

    def test_scan_defaults_to_on(self, pytester):
        config = pytester.parseconfig()
        assert config.getoption("sources_scan") is None
        assert config.getini("sources_scan") is True

    def test_scan_flag_and_ini_turn_it_off(self, pytester):
        assert pytester.parseconfig("--no-sources-scan").getoption("sources_scan") is False
        pytester.makeini("[pytest]\nsources_scan = false\n")
        assert pytester.parseconfig().getini("sources_scan") is False

    def test_defaults_to_no_globs(self, pytester):
        assert pytester.parseconfig().getoption("sources") == []

    def test_accepts_a_glob_verbatim(self, pytester):
        config = pytester.parseconfig("--sources", "submissions/*")
        assert config.getoption("sources") == ["submissions/*"]

    def test_is_repeatable(self, pytester):
        config = pytester.parseconfig("--sources", "submissions/*", "--sources", "other/*")
        assert config.getoption("sources") == ["submissions/*", "other/*"]

    def test_reads_globs_from_ini(self, pytester):
        pytester.makeini("[pytest]\nsources = submissions/* other/*\n")
        assert list(pytester.parseconfig().getini("sources")) == ["submissions/*", "other/*"]

    def test_appears_in_help_under_its_own_group(self, pytester):
        result = pytester.runpytest("--help")
        result.stdout.fnmatch_lines(["sources:", "*--sources=GLOB*"])


def make_sources(pytester, *names):
    for name in names:
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text("X = 1\n")


def collect(pytester, *args):
    result = pytester.runpytest("--collect-only", "-q", *args)
    return [line for line in result.outlines if "::" in line]


def collect_sources(pytester):
    return collect(pytester, "--sources", "submissions/*")


class TestDelimiterOption:
    """Choosing the character that separates parameters in a test id."""

    def test_defaults_to_plus(self, pytester):
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect_sources(pytester)
        assert nodeid.endswith("[submissions/alice+1]")

    def test_the_option_chooses_it(self, pytester):
        make_sources(pytester, "alice")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect(pytester, "--sources", "submissions/*", "--sources-delimiter=@")
        assert nodeid.endswith("[submissions/alice@1]")

    def test_the_ini_chooses_it(self, pytester):
        make_sources(pytester, "alice")
        pytester.makeini("[pytest]\nsources_delimiter = @\n")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect(pytester, "--sources", "submissions/*")
        assert nodeid.endswith("[submissions/alice@1]")

    def test_the_option_beats_the_ini(self, pytester):
        make_sources(pytester, "alice")
        pytester.makeini("[pytest]\nsources_delimiter = @\n")
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.parametrize("n", [1])
            def test_x(source, n): ...
            """
        )

        (nodeid,) = collect(pytester, "--sources", "submissions/*", "--sources-delimiter=%")
        assert nodeid.endswith("[submissions/alice%1]")

    def test_a_source_containing_the_chosen_character_is_rejected(self, pytester):
        (pytester.path / "submissions" / "a@b").mkdir(parents=True)

        with pytest.raises(pytest.UsageError, match="may not appear in a source path"):
            pytester.parseconfigure("--sources", "submissions/*", "--sources-delimiter=@")

    def test_the_default_character_is_free_once_another_is_chosen(self, pytester):
        (pytester.path / "submissions" / f"a{DEFAULT}b").mkdir(parents=True)
        pytester.makepyfile("def test_x(source): ...")

        result = pytester.runpytest("--sources", "submissions/*", "--sources-delimiter=@", "-n", "0")

        result.assert_outcomes(passed=1)

    @pytest.mark.parametrize("bad", ["", "++", "[", "]", "é"])
    def test_an_unusable_character_is_rejected(self, pytester, bad):
        with pytest.raises(pytest.UsageError):
            pytester.parseconfigure(f"--sources-delimiter={bad}")
