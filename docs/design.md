# Antarctic Sea Ice Explorer — Design

## Purpose and runtime

The project is a Reflex research workspace for importing Antarctic observation
CSVs, mapping their geographic and measurement columns, displaying saved
observations on a south-polar globe, and comparing snapshots. It is an
exploratory visualization, not a scientific model or a validated measure of
sea-ice extent.

The configured Reflex application is
[`antarctic_sea_ice_dashboard/antarctic_sea_ice_dashboard.py`](../antarctic_sea_ice_dashboard/antarctic_sea_ice_dashboard.py).
[`rxconfig.py`](../rxconfig.py) sets its database URL and UI plugins. The
separate [`app/`](../app/) tree retains the earlier fixed-grid Overview
implementation; it is not the configured runtime entry point, but remains
covered by regression tests and is kept for reference.

## Core workflows

### Import and configure a dataset

1. A user supplies one UTF-8 CSV and a required year/month snapshot label in
   the Data workspace.
2. The upload is limited to 20 MiB, 120,000 data rows, 10 columns, and 32,768
   characters per cell. Headers and values are retained as strings to preserve
   source spelling and leading zeroes.
3. The CSV parser rejects malformed encodings, duplicate or blank headers,
   malformed rows, invalid quoting, and limit violations before persistence.
4. Dataset metadata and ordered JSON row values are inserted in a database
   transaction. Importing does not silently activate a map layer.
5. A user explicitly maps latitude, longitude, and at least one supported
   numeric measurement; valid mappings can then be activated as globe layers.

The relevant state and persistence logic is in
[`states/uploaded_data.py`](../antarctic_sea_ice_dashboard/states/uploaded_data.py)
and the relational schema is in
[`models.py`](../antarctic_sea_ice_dashboard/models.py). The Data UI is composed
from [`components/uploaded_data.py`](../antarctic_sea_ice_dashboard/components/uploaded_data.py)
and [`components/overview_source.py`](../antarctic_sea_ice_dashboard/components/overview_source.py).

### Explore and compare observations

- Map Explorer groups mapped CSVs by their saved snapshot year/month. Multiple
  enabled CSV layers can be shown for one group. Only finite measurements and
  finite in-range geographic coordinates are rendered.
- The measurement selector only offers supported mapped columns. Sea-ice
  concentration values are converted from fractions to percent when every
  valid reading in that CSV is at most 1; other supported measurements retain
  their observed units.
- Compare pools all eligible mapped files for each of two selected snapshots,
  computes valid-reading means and counts, and optionally builds a difference
  globe from matched 0.5-degree latitude by 1-degree longitude cells.
- Database reads and raster/point preparation run in background workers.
  Request identifiers prevent stale results from replacing newer selections;
  serialized Reflex state carries compact summaries and generated-file
  metadata rather than complete CSV datasets.
- The browser runtime in [`assets/antarctic_globe.js`](../assets/antarctic_globe.js)
  mounts MapLibre and Deck.gl, loads generated point payloads, and handles
  interaction and cleanup when Reflex replaces page elements.

The principal state flows are in
[`states/antarctic_globe.py`](../antarctic_sea_ice_dashboard/states/antarctic_globe.py),
[`states/snapshot_comparison.py`](../antarctic_sea_ice_dashboard/states/snapshot_comparison.py),
and [`states/explorer.py`](../antarctic_sea_ice_dashboard/states/explorer.py).
The shell and page layout are assembled in
[`components/workspace.py`](../antarctic_sea_ice_dashboard/components/workspace.py).

### Prediction comparison in Model Insights

The legacy [`app/`](../app/) workspace adds the ability to classify each CSV as a measurement or
prediction dataset. Measurement datasets remain eligible for the Overview
source; prediction datasets are excluded from Overview and are reserved for
Model Insights. A prediction mapping must use three different available
columns: predicted sea-ice concentration, year, and month. Changing a dataset
to prediction disables its Overview activation.

Model Insights compares the selected prediction CSV with the currently active
Overview measurement CSV. It validates finite concentration values in the
0–100 range and valid year/month pairs, calculates an arithmetic mean for each
dataset and month, and includes only month pairs present in both datasets.
Displayed monthly accuracy is defined here as
`max(0, 100 - abs(predicted_mean - observed_mean))`, in percentage points.
Overall accuracy is the unweighted arithmetic mean of those monthly scores;
months with more source rows are not given extra weight. If no eligible
observation source or no matching valid month exists, the comparison is
unavailable rather than synthesized.

This is a simple descriptive score over user-provided monthly data, not a
trained or validated model, nor a standard classification accuracy measure.
When no prediction dataset is configured, the existing illustrative clustering
demo remains clearly marked as synthetic.

This workflow currently lives in the retained `app/` implementation, not the
configured [`antarctic_sea_ice_dashboard/`](../antarctic_sea_ice_dashboard/)
runtime described above. The default Reflex configuration therefore does not
expose this new prediction workflow; switching the configured app entry point
is a separate integration decision.

The retained [`app/states/overview_grid.py`](../app/states/overview_grid.py)
implements a distinct uploaded-data raster workflow on a 316 × 332 pixel grid.
Its row-order mode, period selection, summary cards, categorical layers, and
pixel inspection behavior are described in
[`uploaded_overview_grid.md`](./uploaded_overview_grid.md).

## Data model and operational assumptions

- Dataset metadata stores the original filename, ordered column names, row
  count, source/status, map activation, and a JSON mapping. Observation rows
  store an ordered JSON array and a stable row position. Dataset deletion
  cascades to its rows.
- Uploads and map sources are shared by all users; the application does not
  provide authentication or per-user data isolation. Do not upload
  confidential or personal information.
- Snapshot year/month are metadata labels for the entire uploaded CSV, not
  values inferred from its rows. Older geographic datasets without date
  metadata remain available as undated layers.
- Latitude/longitude columns are the map position source. A point's visual
  elevation and a comparison cell's bin size are display choices, not
  measurements of thickness, terrain, cell area, or scientific resolution.
- Concentration normalization is applied per CSV under the documented
  all-valid-values-at-most-1 rule. Map Explorer derives one observed
  min/max range per selected measurement across all mapped CSVs, independent
  of snapshot group and layer activation, so the globe colors and legend remain
  comparable when switching dates. The app does not infer a concentration
  unit, validate sensor quality, interpolate observations, or compute
  area-weighted extent.
- The browser requires external access to the basemap and JavaScript/font CDNs.
  Data loading and database failures are shown as errors rather than replaced
  with synthetic data. Unconnected demo pages remain clearly separate from the
  uploaded-observation workflows.
- The legacy grid code and active globe code intentionally coexist; the
  configured app name and route setup determine which tree Reflex launches.
  Removing or migrating the older implementation is outside this documentation
  task.

## Database migrations

[`db_migrations/env.py`](../db_migrations/env.py) resolves model metadata and
supports online/offline Alembic execution. The ordered revisions in
[`db_migrations/versions/`](../db_migrations/versions/) first create the shared
dataset/row tables, then add map-source activation and mapping fields. Each
revision includes a downgrade for its schema changes. The latest revision
adds the measurement/prediction dataset type and saved prediction-column map.

## External libraries, services, and attribution

The following links identify the upstream projects used by the source or
runtime. Python package constraints are recorded in
[`requirements.txt`](../requirements.txt); MapLibre and Deck.gl CDN versions
are pinned in the application entry point.

| Dependency or service | Use | Reference |
|---|---|---|
| Reflex | Python UI, state, events, and database integration | [Reflex documentation](https://reflex.dev/) |
| `xy[reflex]` / `reflex_xy` | Reflex chart data integration | [xy on PyPI](https://pypi.org/project/xy/) |
| SQLAlchemy | ORM models and database queries | [SQLAlchemy documentation](https://www.sqlalchemy.org/) |
| Alembic | Schema migration tooling | [Alembic documentation](https://alembic.sqlalchemy.org/) |
| Psycopg | PostgreSQL driver | [Psycopg documentation](https://www.psycopg.org/) |
| Pillow | Legacy raster creation and image handling | [Pillow documentation](https://python-pillow.org/) |
| Faker | Demo-only synthetic content | [Faker documentation](https://faker.readthedocs.io/) |
| MapLibre GL JS 5.6.1 | Browser map and globe projection | [MapLibre GL JS documentation](https://maplibre.org/maplibre-gl-js/docs/) |
| Deck.gl 9.1.14 | WebGL observation and difference layers | [Deck.gl documentation](https://deck.gl/docs) |
| OpenFreeMap Liberty style | External coastline basemap style | [OpenFreeMap](https://openfreemap.org/) |
| Google Fonts: Inter, IBM Plex Sans | Workspace typography | [Google Fonts](https://fonts.google.com/) |

MapLibre's attribution control remains enabled so the basemap's own attribution
can be displayed. The source CSVs under [`data/`](../data/) are committed as
project inputs but do not include sufficient source/license metadata in their
headers to verify upstream dataset citations or redistribution terms. Their
scientific provenance and license must be confirmed from the original download
records before publication or redistribution; no upstream dataset is asserted
here without that evidence.

## Related documentation

- [`antarctic_globe.md`](./antarctic_globe.md): geographic mapping, globe
  measurements, comparison rules, and limitations.
- [`uploaded_overview_grid.md`](./uploaded_overview_grid.md): retained grid
  renderer semantics and its additional assumptions.
- [`testing.md`](./testing.md): repeatable regression command, coverage, results,
  and debugging notes.
