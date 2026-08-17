# Design

## Package layout

Modules sibling to `plugin.py` correspond to pytest pipeline stages and hold only
hookimpls and fixtures that delegate. Domain logic lives in `_core/`, which defines
no module-level hookimpls and no fixtures; classes there that carry hookimpl methods
(`SourceMaxfail`, `SourceSummary`) are registered at runtime by `_configure`.

Pipeline modules import `_core` only, never each other. `_core` modules import only
downward: `nodeid` ← `source` ← `discover` ← `dist` ← `schedule`.

### Stage order

| # | stage | hook | module |
|---|---|---|---|
| 1 | plugin load | entry point reads the manifest | `plugin.py` |
| 2 | option declaration | `pytest_addoption` | `_options.py` |
| 3 | command line | `pytest_cmdline_main` (the wrapper's pre-yield runs before xdist's; `-n auto` resolves here via `pytest_xdist_auto_num_workers`) | `_cmdline.py`, `_xdist.py` |
| 4 | configure | `pytest_configure`: delimiter, marker scan, patch, plugin registration | `_configure.py` |
| 5 | session start | `pytest_xdist_make_scheduler`, `pytest_configure_node` as workers boot | `_xdist.py` |
| 6 | header | `pytest_report_header` | `_report.py` |
| 7 | collection | `pytest_generate_tests` per test function | `_generate.py` |
| 8 | per-test run | `pytest_runtest_setup` (activation), then the `source` and `_source_cwd` fixtures, then call/teardown, `pytest_runtest_logreport` to the registered classes | `_runtest.py`, `_fixtures.py`, `_core/maxfail.py`, `_core/summary.py` |
| 9 | worker exit | `pytest_testnodedown` starts a replacement process | `_xdist.py` |
| 10 | session end | `pytest_sessionfinish` deactivates the leftover source | `_session.py` |
| 11 | terminal summary | `pytest_terminal_summary` prints the sources table | `_core/summary.py` |
| 12 | unconfigure | `pytest_unconfigure` unpatches and resets the delimiter | `_configure.py` |

Under xdist the controller skips stage 7; workers each collect for themselves and run
stages 4-12 too, minus the controller-only pieces. The marker scan in stage 4 is itself
a nested run of stages 1-7 in scan mode.
