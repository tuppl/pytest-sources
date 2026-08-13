# pytest-sources

pytest-sources is a plugin for pytest that allows tests to be run on multiple sources.

This is handy for autograding coursework, take-home interview screening, and conformance suites across implementation variations.

## Installation

```bash
pip install pytest-sources
```

## Dependencies

This library heavily uses and extends [pytest-xdist](https://github.com/pytest-dev/pytest-xdist).

## Applying sources

The simplest way to use pytest-sources is with:

```bash
pytest --sources "sources/*"
```

The `--sources` flag accepts a path (globbed or exact) targetting the directories of your solutions. `sources/*` means the solutions are each and every subdirectory in `sources/`.

Consider an imaginary `test_add` and sources contains two solutions from `alice` and `bob`. The test suite is parameterised and instantiated against each solution:

```bash
tests/test_add.py::test_add[sources/alice] PASSED
tests/test_add.py::test_add[sources/bob]   FAILED
```

Clearly each source must satisfy some interface such that the test suite can run without error. If there is an error, then pytest will error that test and move onto the next test.

Multiple sources paths can be accumulated:

```bash
pytest --sources "round1/*" --sources "round2/*"
```

If a globbed path doesn't match anything, a usage error will occur.

`--sources` can also be applied in a config file:

```toml
[tool.pytest.ini_options]
sources = ["sources/*"]
```

The flag and the config file do not combine. Any `--sources` on the command line replaces the config file's list entirely.

## Test results

Test results will output a tally table with each source per row:

```
============================== sources ===============================
source          passed  failed  error   skipped xfailed xpassed time
sources/alice   2       0       0       1       0       0       0.01s
sources/bob     1       1       0       1       0       0       0.01s
```

If the tally is not your style, then you can opt for another results table with the `--sources-summary` flag e.g.

```bash
$ pytest --sources "sources/*" --sources-summary sources

source             test_add  test_zero
sources/alice         .          .
sources/bob           F          .
```

The `--sources-summary` flag options are:

| value | rows | columns |
|---|---|---|
| `counts` (default) | source | tally |
| `sources` | source | test case |
| `tests` | test case | source |
| `none` | no table | |

> sources and tests are transposes of each other.

## Parallel testing

Testing many sources sequentially can be long. Testing many untrusted sources in a single process brings the risk of crashing the entire test suite. This library extends `pytest-xdist` to enable parallel testing such that each source is isolated and tested in its own process. The number of workers can be set with the [-n](https://pytest-xdist.readthedocs.io/en/stable/distribution.html) flag:

```bash
pytest --sources "sources/*"        # default: -n auto
pytest --sources "sources/*" -n 4   # 4 workers
```

The testing of a source is grouped as a single work item:
- A work item is a unit of work that is consumed by a worker (one-at-a-time).
- Each work item runs in its own process.
- A work item deals with exactly one source.
- A work item deals with a subset or the entire test suite for that one source.
- If a work item crashes, it will restart as many times [--max-worker-restart](https://pytest-xdist.readthedocs.io/en/stable/crash.html) allows it to.

When:
- `num_worker <= num_source`: each testing of a source is a work item, with surplus work items queued.
- `num_worker > num_source`: each source is split into `num_worker / num_source` work items.

Parallel testing can be disabled with `-n 0` or `--dist no` which disables source isolation in a process. Every source will be tested in the calling process.

> pytest-xdist assumes number of workers and number of processes to be one-to-one. But pytest-sources has decoupled this by allowing workers to shutdown and spin-up new processes with a worker.

## Parallel testing groups

Testing of a source can be further grouped to create more work items with the [--dist](https://pytest-xdist.readthedocs.io/en/stable/distribution.html#running-tests-across-multiple-cpus:~:text=The%20test%20distribution%20algorithm%20is%20configured%20with%20the%20%2D%2Ddist%20command%2Dline%20option%3A) flag:

```bash
pytest --sources "sources/*" --dist loadfile -n 4
```
For example if `loadfile` was set, and if there were 10 sources and 3 test files, then 10 sources × 3 test files = 30 work items. As opposed to the default 10 work items for 10 sources.

The supported `--dist` options are:

| `--dist` | work item for each |
|---|---|
| `load` (default) | source |
| `loadfile` | source × test file |
| `loadscope` | source × (module or class) |
| `loadgroup` | source × `xdist_group` |

### Using `loadgroup`

```bash
pytest --sources "sources/*" --dist loadgroup -n 4
```

```python
@pytest.mark.xdist_group("database")
def test_writes(source): ...


@pytest.mark.xdist_group("database")
def test_reads(source): ...
```

## Source fixture

A `source` fixture is provided with the following properties and methods:

| | |
|---|---|
| `source.id` | The source path relative to the rootdir, as it appears in the test id. |
| `source.name` | The directory name on its own. |
| `source.path` | The directory as a `Path`. |
| `source / "data.txt"` | A path inside the source; `source` is path-like. |
| `source.import_module("solution")` | Import that reports a missing file as one line rather than a traceback. |
| `source.chdir()` | Move into the source by hand. |

```python
def test_add(source):
    solution = source.import_module("solution")
    assert solution.add(2, 3) == 5


def test_has_a_readme(source):
    assert (source / "README.md").exists()
```

## Importing source code

Module-level imports of source code are **not** supported because this conflicts with pytest-sources' per-source model:

```python
import solution  # ModuleNotFoundError during collection


def test_add(source): ...
```

To work around this, the source directory is automatically added to `sys.path` and you should import code within the test function to ensure the import is per-source:

```python
def test_add():
    import solution
```

Or equivalently with the `source` fixture:

```python
def test_add(source):
    solution = source.import_module("solution")
```

## Working directory

Tests will automatically change the working directory to the source directory. Relative paths are resolvable relative to a source:

```python
def read():
    return open("data.txt").read()  # data.txt beside solution.py
```

Or in a test:

```python
def test_reads_the_sources_data(source):
    from solution import read

    assert read().strip() == source.name
```

Opt out of this automatic behaviour with `no_chdir` which will instead change the working directory to where pytest was started:

```python
@pytest.mark.no_chdir
def test_reads_a_fixture(source):
    assert open("tests/data/expected.json").read()
```

You can programmatically change directory to the source with `source.chdir()`:

```python
@pytest.mark.no_chdir
def test_output_matches_the_expected_file(source):
    expected = open("tests/data/expected.txt").read()

    with source.chdir():
        actual = open("output.txt").read()

    assert actual == expected
```

## Applying sources per test

A test case can be narrowed to be parameterised on a subset of the provided sources:

```python
@pytest.mark.sources("sources/*_alt")
def test_sources_decorator(source): ...
```

`test_sources_decorator` does not run on every sources subdirectory but only on subdirectories that end with `_alt`.

A glob matching a directory that `--sources` did not provide is a usage error.

To run a test with the normal pytesting behaviour i.e. only once regardless of `--sources`:

```python
@pytest.mark.no_sources
def test_helper(): ...
```

Or put `pytestmark = pytest.mark.no_sources` at module level to exempt a whole file.

## Stopping a source early

A source can be given a max limit of failures with the `--sources-maxfail` flag. When the source exhausts it, the remaining tests for that source are skipped:

```bash
$ pytest --sources "sources/*" --sources-summary sources --sources-maxfail=1

source             test_one  test_two  test_three
sources/alice         .         .           .
sources/bob           F         s           s
```

This flag is incompatible with `loadfile`, `loadscope` or `loadgroup`.

## Limitations

### Parameterised test ID

Pytest's default parameterised node ID delimiter uses `-`. This could mean a source `alice` with parameter `3` will have the same node id as a source `alice-3`:

```bash
tests/test_add.py::test_add[sources/alice-3]
```

This conflicts with our per-source model since `-` is a valid directory character symbol. We patch this to use `+` since this is an unlikely symbol to use.

No source path may contain the delimiter otherwise an error will occur. If your sources do contain `+`, you can change the delimiter:

```bash
pytest --sources "sources/*" --sources-delimiter="#"
```

```
tests/test_add.py::test_add[sources/alice]
tests/test_add.py::test_add[sources/alice#3]
```

The delimiter must be one printable ASCII character, and cannot be `[` or `]`.

Alternatively in an ini:

```toml
[tool.pytest.ini_options]
sources_delimiter = "#"
```

### Hanging code

This library doesn't handle code stuck in an infinite loop. We recommend you use [pytest-timeout](https://github.com/pytest-dev/pytest-timeout).

## Todo

- Support for `--dist each` and `--dist worksteal`.
- More efficient worker scheduling. 6 workers with 3 sources and 2 work items each has all 6 workers busy. However, 5 workers with 3 sources and 1 work item each has 2 workers idling.
- More efficient test collection. All tests are collected again per source spin-up.
