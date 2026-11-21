# Test Cases, Results, and Debugging Notes

## Test command

The regression suite uses Python's standard-library `unittest` and lives in
[`scripts/`](../scripts/). Reflex permits direct state construction in tests
only when its `PYTEST_CURRENT_TEST` environment marker is set. The suite can be
run without installing another test framework by using this PowerShell command
from the repository root:

```powershell
@'
import os
import logging
import sys
import unittest

os.environ["PYTEST_CURRENT_TEST"] = "unittest-discovery"
logging.getLogger().setLevel(logging.CRITICAL)
suite = unittest.defaultTestLoader.discover("scripts")
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())
'@ | py -3.13 -
```

The marker is set before test modules import Reflex state classes. It enables
Reflex's existing test-only construction path; it does not change application
code or test assertions.

## Coverage

| Test module | Cases covered |
|---|---|
| [`test_csv_validation.py`](../scripts/test_csv_validation.py) | UTF-8/BOM decoding, quoted values, string preservation, CSV size/row/column limits, malformed files, snapshot-date validation, geographic/measurement mapping suggestions and validation. |
| [`test_antarctic_globe.py`](../scripts/test_antarctic_globe.py) | Geographic mapping requirements, legacy undated sources, snapshot grouping, active-layer batching, invalid observation handling, cross-snapshot shared color ranges, measurement scaling, and comparison summaries/difference cells. |
| [`test_overview_grid.py`](../scripts/test_overview_grid.py) | Grid coordinate bounds and corners, row-order mode, numeric and categorical raster behavior, duplicate ownership, transparent missing cells, saved-row lookup, bounded result metadata, database failure reporting, and generated-file cleanup. |
| [`test_overview_periods.py`](../scripts/test_overview_periods.py) | Available year/month periods, undated and partially dated sources, invalid dates/readings, period-specific raster/card/monthly aggregation, manual dates, pixel inspection, stale request protection, and supported period controls. |
| [`test_prediction_comparison.py`](../scripts/test_prediction_comparison.py) | Prediction mapping validation, filtering invalid measurements/dates, monthly averaging, matched-month-only scoring, and unavailable comparisons when no month matches. |

The grid tests exercise the retained `app/` implementation as well as the
active geographic workflow's tests; they are not browser end-to-end tests.
Database interactions are mocked or use in-memory fixtures, so the suite does
not certify a production database connection, external CDN availability,
browser rendering, or performance against a production-scale deployment.

## Results

Validation run on 2026-11-16 with Python 3.13:

| Run | Result |
|---|---|
| Full `unittest` discovery under Reflex test mode | **69 tests passed** in 16.791 seconds. |
| Python syntax parsing | **39 Python source files parsed successfully** with Python 3.13. |

No latency or throughput benchmark is included. The test timings above are
local regression-suite duration, not a product performance claim.

## Debugging notes

- An initial plain `py -3.13 -m unittest discover -s scripts -v` run executed
  the suite but reported three errors where tests instantiate Reflex state
  objects directly. The exception came from Reflex's intentional guard against
  state construction outside test mode, not from a failed application
  assertion.
- Running the same discovered tests after setting
  `PYTEST_CURRENT_TEST=unittest-discovery` before test-module import passed all
  69 tests. This is the documented command above.
- The direct `pytest` command was not available in the local Python 3.13
  environment. No dependency was added because the project already uses
  `unittest`, and the documented invocation exercises the complete existing
  suite.
- Globally disabling logging with `logging.disable()` breaks tests that verify
  expected error logs using `assertLogs`. Setting the root logger's level to
  `CRITICAL` instead suppresses routine negative-path output while preserving
  those assertions.
- The editor's selected Pylance environment reports unresolved imports for
  installed project dependencies such as Reflex and SQLAlchemy. These are
  environment diagnostics also present before the documentation/comment
  changes. Configure VS Code to use the project's Python environment before
  treating editor import diagnostics as code errors.
- Expected negative-path logging in CSV, database, and file-write tests is
  intentional; tests assert the corresponding user-facing error and cleanup
  behavior.

Update the results table whenever a test suite is rerun after implementation
changes. Add new regression cases alongside the feature they protect, and
distinguish mocked unit coverage from browser, database-integration, and
performance testing.
