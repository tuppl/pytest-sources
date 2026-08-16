import pytest

from pytest_sources._core.dist import Dist, request_dist


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
