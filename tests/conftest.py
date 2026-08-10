import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def submissions(pytester):
    """Three sources, two tests each, for the scheduling and worker-count tests."""
    for name in ("alice", "bob", "carol"):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text(f"VALUE = {name!r}\n")
    pytester.makepyfile(
        """
        def test_one(source):
            assert source.import_module("solution").VALUE == source.name

        def test_two(source):
            assert (source / "solution.py").exists()
        """
    )
    return pytester
