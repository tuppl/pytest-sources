# Each module implements one stage of the pytest pipeline and no two implement
# the same hook, so the order here is readability, not behaviour.
pytest_plugins = [
    "pytest_sources._options",
    "pytest_sources._cmdline",
    "pytest_sources._configure",
    "pytest_sources._generate",
    "pytest_sources._fixtures",
    "pytest_sources._runtest",
    "pytest_sources._session",
    "pytest_sources._xdist",
]
