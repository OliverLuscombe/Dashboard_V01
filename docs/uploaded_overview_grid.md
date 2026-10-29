# Uploaded Overview pixel grid

Overview loads the explicitly applied CSV source on initial page load, on navigation back to Overview, and with **Refresh source / Refresh map**. Applying a source in Data does not transform or validate its measurements. Map Explorer, Compare, and Model Insights retain their synthetic demos. Overview summaries, seasonal chart, and model teaser are hidden while a source is loading, active, or in error. The existing demo period controls do not filter the uploaded grid.

## Coordinates and missing values

- The raster is exactly 316 columns by 332 rows. CSV `(1, 332)` is the top-left image pixel `(0, 0)`; CSV `(316, 1)` is the bottom-right image pixel `(315, 331)`.
- Explicit x/y cells must parse as finite integers within x=1–316 and y=1–332. Decimal integer notation such as `3.0` is accepted. Latitude and longitude are optional inspector metadata, never positioning substitutes.
- Row-order mode revalidates that every stored position 0–104,911 exists exactly once before rendering or inspection. Position `p` maps to x=`p % 316 + 1`, y=`332 - p // 316`. Metadata row count alone is not sufficient.
- Rows are ordered by saved position and ID. The first row with a valid coordinate owns that pixel even when its selected measurement is invalid. Later rows at the same coordinate are counted as duplicates and ignored. Dates are not interpreted in this phase; overlapping dated observations are not averaged or selected by period.
- Numeric measurements accept finite values, including zero. Empty, nonnumeric, NaN and infinite values are transparent. This is parsing, not scientific range or quality validation; the app does not enforce concentration percentages or temperature/wind validity.
- Mapped marginal-ice-zone and cluster columns are rendered as discrete CSV labels, not inferred ice zones or computed clusters. Labels are whitespace-trimmed but otherwise preserved, including distinct numeric spellings. Empty/NA/null/non-finite labels and labels longer than 120 characters are missing. More than 32 distinct valid categories produces a clear error instead of merging categories or sending an unbounded legend.

The viewer reports valid unique rendered pixels, examined rows, invalid coordinates/malformed rows, duplicate coordinates and invalid readings. For successful or empty renders, examined rows equal valid pixels plus the three skipped-row counts. Transparent pixels equal 104,912 minus valid pixels; skipped rows and missing grid cells are different quantities.

Continuous colours use the observed minimum and maximum of rendered pixels, with a midpoint colour for constant values. Discrete colours and legend labels come from actual values. The neutral background is not a reading. No coastline, graticule, region pins, interpolation, distance scale or scientific projection is added.

## Loading, inspection, and refresh

No active source returns to the unchanged demo. Missing measurement mapping, no valid readings, loading, and database/renderer failures have distinct states; a failed source read never falls back silently to synthetic observations.

The inspector reads current saved data with the same coordinate and first-row rules. It displays all mapped readings, identifies the selected measurement, and shows optional finite latitude/longitude within their metadata bounds. A missing coordinate says **No observation at that pixel**; a stored row with an invalid measurement says **no valid reading**. Refresh the raster after edits so its snapshot matches the current inspector. Replacing or deleting the active source requires refreshing Overview.

Big reads and Pillow rendering run off the event loop in background events. State locks are used only for state updates. Reads use a consistent snapshot and streamed, ordered, bounded row queries; raw CSV rows and the full pixel arrays are never put in serialized Reflex state. Request identifiers prevent slower obsolete renders or inspections from overwriting newer selections.

Runtime PNGs are created using Reflex's served upload directory and displayed with its upload-URL helper, not the static assets directory. Each completed refresh uses a new filename and removes the previous generated files for that session; stale render outputs and partial write failures are cleaned up. The database remains the source of record and no schema changes are made.

## Regression coverage

`scripts/test_overview_grid.py` covers coordinate corners, full row-order rasterization, finite numeric parsing, bounds, duplicates, transparent missing cells, constant and extreme numeric ranges, categorical legends and category limits, intact-position validation, source loading, compact PNG output, actual pixel lookup, database failures and file-write cleanup. It uses pure raster inputs and mocked reads, not a fabricated saved dataset. Existing CSV/mapping coverage remains in `scripts/test_csv_validation.py`.
