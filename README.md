# pytest-sources

[![PyPI](https://img.shields.io/pypi/v/pytest-sources)](https://pypi.org/project/pytest-sources/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-sources)](https://pypi.org/project/pytest-sources/)
[![Tests](https://github.com/tuppl/pytest-sources/actions/workflows/ci.yml/badge.svg)](https://github.com/tuppl/pytest-sources/actions/workflows/ci.yml)

pytest-sources is a plugin for pytest that allows tests to be run on multiple sources.

This is handy for autograding coursework, take-home interview screening, and conformance suites across implementation variations.

The full guide lives in [docs/GUIDE.md](docs/GUIDE.md); the internals are described in [docs/DESIGN.md](docs/DESIGN.md).

## Features

- Run one test suite against many source directories, each test parameterised per source.
- One process per source isolation enabled when using `-n`.
- Per-source results table, with grid views of source × test.
- Per-source failure budget with `--sources-maxfail`.
- Tests run with the source on `sys.path` and as the working directory, so submissions can import and read their own files.
- Sources per test via `@pytest.mark.sources`, opt-outs via `no_sources` and `no_chdir`.

## Installation

```bash
pip install pytest-sources
```

## Quick start

```bash
pytest --sources "sources/*" -n auto
```

```python
def test_add(source):
    solution = source.import_module("solution")
    assert solution.add(2, 3) == 5
```

```
tests/test_add.py::test_add[sources/alice] PASSED
tests/test_add.py::test_add[sources/bob]   FAILED
```

> See [`source`'s full API](docs/GUIDE.md#source-fixture) for `import_module`, `chdir`, and the rest.

## Reference

### Options

| option | ini | default | description |
|---|---|---|---|
| `--sources GLOB` (repeatable) | `sources = [...]` | none | Run every test once per matching source directory. The option replaces the ini list. |
| `-n N` / `-n auto` | | `0` | Workers ([pytest-xdist](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)). `auto` starts one worker per source, capped at the CPU count. Without workers, sources share one process and lose isolation. |
| `--dist MODE` | | `load` | Split a source into more work items: `loadfile`, `loadscope`, `loadgroup`. |
| `--sources-summary VIEW` | | `counts` | View test results as a table with options: `counts`, `sources`, `tests`, `none`. |
| `--sources-maxfail N` | | `0` (off) | Per-source failure budget. Exact by default, approximate when a `--dist` grouping mode splits the source over processes. |
| `--sources-delimiter CHAR` | `sources_delimiter` | `+` | Separator between parameters in a test id. No source path may contain it. |
| `--skip-marker-sources` | `skip_marker_sources` | `false` | Skip tests with the `sources` marker. |

### Markers

| marker | description |
|---|---|
| `@pytest.mark.sources(*globs)` | Run this test against its own sources instead of the `--sources` set. |
| `@pytest.mark.no_sources` | Run this test once, exempt from being tested against each source. |
| `@pytest.mark.no_chdir` | Keep the working directory pytest was started in. |

## Todo

- Support for `--dist each` and `--dist worksteal`.
- More efficient test collection. All tests are collected again per source spin-up.
