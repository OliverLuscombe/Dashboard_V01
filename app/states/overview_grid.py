import reflex as rx
import asyncio
import calendar
import reflex_xy as xy
import base64
import colorsys
import io
import json
import logging
import math
import re
from array import array
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import uuid4

from PIL import Image
from sqlalchemy import func, select
from app.models import UploadedDataset, UploadedDatasetRow
from app.states.uploaded_data import (
    GRID_ROWS,
    MAX_ROWS,
    MAPPING_LABELS,
    UploadedData,
)


MEASUREMENTS: dict[str, str] = {
    "sea_ice_concentration": "Sea ice concentration (%)",
    "sea_surface_temperature": "Sea-surface temperature (°C)",
    "wind_speed": "Wind speed (m/s)",
    "air_temperature": "Air temperature (°C)",
    "marginal_ice_zone": "Marginal ice zone · CSV categories",
    "cluster": "Cluster · CSV labels",
}
DISCRETE = ("marginal_ice_zone", "cluster")
CATEGORY_LIMIT = 32
NUMERIC_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",
    re.ASCII,
)


class GridLayer(TypedDict):
    key: str
    label: str
    column: str


class GridLegend(TypedDict):
    label: str
    swatch: str


class GridPeriod(TypedDict):
    year: int
    month: int


class GridMetric(TypedDict):
    label: str
    value: str
    method: str


class MonthlyReading(TypedDict):
    month: int
    mean: float
    count: int


class GridResult(TypedDict):
    periods: list[GridPeriod]
    year: int
    month: int
    dated_year: bool
    dated_month: bool
    year_source: str
    month_source: str
    invalid_dates: int
    period_rows: int
    metrics: list[GridMetric]
    monthly: list[MonthlyReading]
    chart_reason: str
    status: str
    source_id: int
    name: str
    layer: str
    layers: list[GridLayer]
    column: str
    coordinate_mode: str
    filename: str
    legend_filename: str
    legends: list[GridLegend]
    minimum: str
    maximum: str
    total: int
    valid: int
    invalid_coordinates: int
    duplicates: int
    invalid_readings: int
    message: str


class OverviewGrid(rx.State):
    periods: list[GridPeriod] = []
    selected_year: int = 0
    selected_month: int = 0
    dated_year: bool = False
    dated_month: bool = False
    year_source: str = "Not provided"
    month_source: str = "Not provided"
    invalid_dates: int = 0
    period_rows: int = 0
    metrics: list[GridMetric] = []
    monthly: list[MonthlyReading] = []
    chart_reason: str = "Loading saved observations…"
    playing: bool = False
    play_id: int = 0
    status: str = "loading"
    source_id: int = 0
    source_name: str = ""
    selected_layer: str = ""
    layers: list[GridLayer] = []
    column: str = ""
    coordinate_mode: str = ""
    filename: str = ""
    legend_filename: str = ""
    legends: list[GridLegend] = []
    minimum: str = ""
    maximum: str = ""
    total: int = 0
    valid: int = 0
    invalid_coordinates: int = 0
    duplicates: int = 0
    invalid_readings: int = 0
    message: str = "Loading the saved Overview source…"
    updated: str = ""
    request_id: int = 0
    inspect_id: int = 0
    inspection: str = (
        "Enter a pixel coordinate to inspect its saved observation."
    )
    inspecting: bool = False
    inspection_details: list[dict[str, str]] = []

    @rx.var
    def period_label(self) -> str:
        if not self.dated_year and not self.dated_month:
            return "Undated snapshot"
        if not self.periods:
            return "No valid mapped dates"
        month = (
            calendar.month_name[self.selected_month]
            if self.selected_month
            else ""
        )
        year = str(self.selected_year) if self.selected_year else ""
        return f"{month} {year}".strip()

    @rx.var
    def years(self) -> list[str]:
        return [
            str(y)
            for y in sorted({p["year"] for p in self.periods if p["year"]})
        ]

    @rx.var
    def months(self) -> list[str]:
        return [
            str(m)
            for m in sorted(
                {
                    p["month"]
                    for p in self.periods
                    if p["year"] == self.selected_year and p["month"]
                }
            )
        ]

    @xy.data
    def seasonal(self) -> dict[str, list[float]]:
        return {
            "month": [float(row["month"]) for row in self.monthly],
            "mean": [row["mean"] for row in self.monthly],
        }

    @rx.var
    def label(self) -> str:
        return MEASUREMENTS.get(self.selected_layer, "Measurement not mapped")

    @rx.var
    def discrete(self) -> bool:
        return self.selected_layer in DISCRETE

    @rx.var
    def skipped(self) -> int:
        return (
            self.invalid_coordinates + self.duplicates + self.invalid_readings
        )

    @staticmethod
    def _number(value: object) -> float | None:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            return None
        raw = str(value).strip()
        if not NUMERIC_PATTERN.fullmatch(raw):
            return None
        number = float(raw)
        return number if math.isfinite(number) else None

    @staticmethod
    def _cells(raw: str, column_count: int) -> list[str] | None:
        try:
            cells = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(cells, list) or len(cells) != column_count:
            return None
        if not all(isinstance(cell, str) for cell in cells):
            return None
        return cells

    @staticmethod
    def _coordinate(
        position: int,
        cells: list[str] | None,
        indices: dict[str, int],
        mode: str,
    ) -> tuple[int, int] | None:
        if mode == "row_order":
            return UploadedData._pixel_coordinates(position)
        if cells is None:
            return None
        x = OverviewGrid._number(cells[indices["x_coordinate"]])
        y = OverviewGrid._number(cells[indices["y_coordinate"]])
        if x is None or y is None or not x.is_integer() or not y.is_integer():
            return None
        if not 1 <= x <= 316 or not 1 <= y <= 332:
            return None
        return int(x), int(y)

    @staticmethod
    def _category(raw: str) -> str | None:
        value = raw.strip()
        if not value or value.casefold() in {
            "na",
            "n/a",
            "nan",
            "null",
            "none",
            "inf",
            "+inf",
            "-inf",
            "infinity",
            "+infinity",
            "-infinity",
        }:
            return None
        if len(value) > 120:
            return None
        try:
            number = float(value)
        except ValueError:
            return value
        except OverflowError:
            logging.exception("Unexpected error")
            return None
        return value if math.isfinite(number) else None

    @staticmethod
    def _indices(columns: list[str], mapping: dict[str, str]) -> dict[str, int]:
        return {
            key: columns.index(value)
            for key, value in mapping.items()
            if key in MAPPING_LABELS and value
        }

    @staticmethod
    def _check_positions(session, dataset_id: int):
        count, distinct, first, last = session.execute(
            select(
                func.count(UploadedDatasetRow.id),
                func.count(func.distinct(UploadedDatasetRow.row_position)),
                func.min(UploadedDatasetRow.row_position),
                func.max(UploadedDatasetRow.row_position),
            ).where(UploadedDatasetRow.dataset_id == dataset_id)
        ).one()
        if (
            count != GRID_ROWS
            or distinct != GRID_ROWS
            or first != 0
            or last != GRID_ROWS - 1
        ):
            raise ValueError(
                "Row-order coordinates are unavailable: the saved grid must contain every position 0–104,911 exactly once. Re-import an intact grid or map explicit x/y columns in Data."
            )

    @staticmethod
    def _base_result() -> GridResult:
        return {
            "periods": [],
            "year": 0,
            "month": 0,
            "dated_year": False,
            "dated_month": False,
            "year_source": "Not provided",
            "month_source": "Not provided",
            "invalid_dates": 0,
            "period_rows": 0,
            "metrics": [],
            "monthly": [],
            "chart_reason": "No uploaded source.",
            "status": "demo",
            "source_id": 0,
            "name": "",
            "layer": "",
            "layers": [],
            "column": "",
            "coordinate_mode": "",
            "filename": "",
            "legend_filename": "",
            "legends": [],
            "minimum": "",
            "maximum": "",
            "total": 0,
            "valid": 0,
            "invalid_coordinates": 0,
            "duplicates": 0,
            "invalid_readings": 0,
            "message": "",
        }

    @staticmethod
    def _raster(
        rows: Iterable[tuple[int, str]],
        columns: list[str],
        mapping: dict[str, str],
        layer: str,
        result: GridResult,
    ) -> tuple[Image.Image, Image.Image]:
        indices = OverviewGrid._indices(columns, mapping)
        values = array("d", [math.nan]) * GRID_ROWS
        occupied = bytearray(GRID_ROWS)
        categories: dict[str, int] = {}
        discrete = layer in DISCRETE
        for position, raw in rows:
            result["total"] += 1
            if result["total"] > MAX_ROWS:
                raise ValueError(
                    "This source exceeds the supported 120,000-row limit."
                )
            cells = OverviewGrid._cells(raw, len(columns))
            coordinate = OverviewGrid._coordinate(
                position, cells, indices, mapping["coordinate_mode"]
            )
            if coordinate is None:
                result["invalid_coordinates"] += 1
                continue
            x, y = coordinate
            offset = (332 - y) * 316 + x - 1
            if occupied[offset]:
                result["duplicates"] += 1
                continue
            occupied[offset] = 1
            raw_value = (
                cells[indices[layer]]
                if cells is not None and layer in indices
                else ""
            )
            if discrete:
                category = OverviewGrid._category(raw_value)
                if category is not None:
                    if category not in categories:
                        if len(categories) >= CATEGORY_LIMIT:
                            raise ValueError(
                                "This discrete layer has more than 32 categories. Use a categorical column with at most 32 distinct labels; no categories were silently merged."
                            )
                        categories[category] = len(categories)
                    value = float(categories[category])
                else:
                    value = None
            else:
                value = OverviewGrid._number(raw_value)
            if value is None:
                result["invalid_readings"] += 1
                continue
            values[offset] = value
            result["valid"] += 1
        image = Image.new("RGBA", (316, 332), (0, 0, 0, 0))
        gradient = Image.new("RGB", (256, 1))
        gradient.putdata(
            [OverviewGrid._continuous_color(i / 255) for i in range(256)]
        )
        if not result["valid"]:
            return image, gradient
        valid_values = [value for value in values if math.isfinite(value)]
        low, high = min(valid_values), max(valid_values)
        result["minimum"], result["maximum"] = f"{low:.6g}", f"{high:.6g}"
        palette = [
            tuple(
                round(channel * 255)
                for channel in colorsys.hsv_to_rgb(
                    (i * 0.61803398875) % 1, 0.62, 0.72
                )
            )
            for i in range(len(categories))
        ]
        if discrete:
            result["legends"] = []
            for label, index in categories.items():
                swatch = Image.new("RGB", (1, 1), palette[index])
                buffer = io.BytesIO()
                swatch.save(buffer, format="PNG")
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                result["legends"].append(
                    {
                        "label": label,
                        "swatch": f"data:image/png;base64,{encoded}",
                    }
                )
        scale = max(abs(low), abs(high)) or 1.0
        span = high / scale - low / scale
        pixels = image.load()
        for offset, value in enumerate(values):
            if math.isfinite(value):
                color = (
                    palette[int(value)]
                    if discrete
                    else OverviewGrid._continuous_color(
                        (value / scale - low / scale) / span if span else 0.5
                    )
                )
                pixels[offset % 316, offset // 316] = (*color, 255)
        return image, gradient

    @staticmethod
    def _period(
        cells: list[str] | None,
        indices: dict[str, int],
        mapping: dict[str, str] | None = None,
    ) -> tuple[int, int] | None:
        fixed = UploadedData._fixed_dates(mapping or {})
        dates = []
        for key, bound in (("year", 9999), ("month", 12)):
            if key not in indices:
                dates.append(
                    int(fixed[f"fixed_{key}"]) if fixed[f"fixed_{key}"] else 0
                )
                continue
            value = OverviewGrid._number(cells[indices[key]]) if cells else None
            if (
                value is None
                or not value.is_integer()
                or not 1 <= value <= bound
            ):
                return None
            dates.append(int(value))
        return dates[0], dates[1]

    @staticmethod
    def _scan(
        rows: Iterable[tuple[int, str]],
        columns: list[str],
        mapping: dict[str, str],
        layer: str,
        result: GridResult,
        year: int = 0,
        month: int = 0,
    ) -> tuple[Image.Image, Image.Image]:
        indices = OverviewGrid._indices(columns, mapping)
        fixed = UploadedData._fixed_dates(mapping)
        for key in ("year", "month"):
            result[f"dated_{key}"] = key in indices or bool(
                fixed[f"fixed_{key}"]
            )
            result[f"{key}_source"] = (
                f"CSV column: {mapping[key]}"
                if key in indices
                else f"Manual metadata for every row: {fixed[f'fixed_{key}']}"
                if fixed[f"fixed_{key}"]
                else "Not provided"
            )
        chosen = (
            year if result["dated_year"] else 0,
            month if result["dated_month"] else 0,
        )
        automatic = not year and not month
        selected: list[tuple[int, str]] = []
        periods: set[tuple[int, int]] = set()
        seen: set[tuple[int, int, int, int]] = set()
        monthly: dict[tuple[int, int], tuple[float, int]] = {}
        examined = 0
        for position, raw in rows:
            examined += 1
            if examined > MAX_ROWS:
                raise ValueError(
                    "This source exceeds the supported 120,000-row limit."
                )
            cells = OverviewGrid._cells(raw, len(columns))
            period = OverviewGrid._period(cells, indices, mapping)
            if period is None:
                result["invalid_dates"] += 1
                continue
            periods.add(period)
            if automatic and (len(periods) == 1 or period < chosen):
                if period != chosen:
                    selected.clear()
                chosen = period
            if period == chosen:
                selected.append((position, raw))
            coordinate = OverviewGrid._coordinate(
                position, cells, indices, mapping["coordinate_mode"]
            )
            if coordinate is None:
                continue
            identity = (*period, *coordinate)
            if identity in seen:
                continue
            seen.add(identity)
            if "sea_ice_concentration" in indices and cells:
                value = OverviewGrid._number(
                    cells[indices["sea_ice_concentration"]]
                )
                if value is not None and 0 <= value <= 100:
                    mean, count = monthly.get(period, (0.0, 0))
                    monthly[period] = (
                        mean + (value - mean) / (count + 1),
                        count + 1,
                    )
        result["periods"] = [
            {"year": y, "month": m} for y, m in sorted(periods)
        ]
        result["year"], result["month"] = chosen
        result["period_rows"] = len(selected)
        result["monthly"] = [
            {"month": m, "mean": mean, "count": count}
            for (y, m), (mean, count) in sorted(monthly.items())
            if m and y == chosen[0]
        ]
        result["chart_reason"] = (
            "Not available · month column not mapped and no manual month provided"
            if not result["dated_month"]
            else "Not available · concentration column not mapped"
            if "sea_ice_concentration" not in indices
            else "Not available · fewer than two observed months with valid concentration readings (0–100%). A fixed month supplies one month only; no seasonal series is synthesized."
            if len(result["monthly"]) < 2
            else ""
        )
        occupied: set[tuple[int, int]] = set()
        means: dict[str, tuple[float, int]] = {}
        categories: dict[str, set[str]] = {key: set() for key in DISCRETE}
        category_counts = {key: 0 for key in DISCRETE}
        threshold = 0
        for position, raw in selected:
            cells = OverviewGrid._cells(raw, len(columns))
            coordinate = OverviewGrid._coordinate(
                position, cells, indices, mapping["coordinate_mode"]
            )
            if coordinate is None or coordinate in occupied or cells is None:
                continue
            occupied.add(coordinate)
            for key in ("sea_ice_concentration", "sea_surface_temperature"):
                if key not in indices:
                    continue
                value = OverviewGrid._number(cells[indices[key]])
                if value is None or (
                    key == "sea_ice_concentration" and not 0 <= value <= 100
                ):
                    continue
                mean, count = means.get(key, (0.0, 0))
                means[key] = (
                    mean * (count / (count + 1)) + value / (count + 1),
                    count + 1,
                )
                if key == "sea_ice_concentration" and value >= 15:
                    threshold += 1
            for key in DISCRETE:
                if key in indices:
                    category = OverviewGrid._category(cells[indices[key]])
                    if category is not None:
                        categories[key].add(category)
                        category_counts[key] += 1
        for key, label, unit in (
            ("sea_ice_concentration", "Mean concentration", "%"),
            ("sea_surface_temperature", "Mean sea-surface temperature", "°C"),
            ("cluster", "Distinct CSV cluster labels", "labels"),
            ("marginal_ice_zone", "Distinct MIZ categories", "categories"),
        ):
            count = (
                category_counts.get(key, 0)
                if key in DISCRETE
                else means.get(key, (0.0, 0))[1]
            )
            value = (
                f"{len(categories[key]):,} {unit}"
                if key in DISCRETE
                else f"{means.get(key, (0.0, 0))[0]:.2f} {unit}"
            )
            result["metrics"].append(
                {
                    "label": label,
                    "value": value if count else "Not available",
                    "method": f"n = {count:,} unique pixels · selected period"
                    if count
                    else "Column not mapped"
                    if key not in indices
                    else "No valid values in selected period",
                }
            )
        count = means.get("sea_ice_concentration", (0.0, 0))[1]
        result["metrics"].insert(
            1,
            {
                "label": "Pixels with concentration ≥15%",
                "value": f"{threshold:,} pixels" if count else "Not available",
                "method": f"n = {count:,} · pixel count, NOT area or extent"
                if count
                else "Column not mapped"
                if "sea_ice_concentration" not in indices
                else "No valid values in selected period",
            },
        )
        images = OverviewGrid._raster(selected, columns, mapping, layer, result)
        result["total"] = examined
        return images

    @staticmethod
    def _continuous_color(fraction: float) -> tuple[int, int, int]:
        fraction = min(1.0, max(0.0, fraction))
        return tuple(
            round(start + (end - start) * fraction)
            for start, end in zip((225, 245, 250), (15, 76, 112))
        )

    @staticmethod
    def _render(
        preferred: str, year: int = 0, month: int = 0, source_id: int = 0
    ) -> GridResult:
        result = OverviewGrid._base_result()
        with rx.session() as session:
            session.connection(
                execution_options={"isolation_level": "REPEATABLE READ"}
            )
            dataset = session.scalar(
                select(UploadedDataset)
                .where(UploadedDataset.overview_active.is_(True))
                .order_by(UploadedDataset.id)
                .limit(1)
            )
            if dataset is None:
                return result
            result["source_id"], result["name"] = dataset.id, dataset.name
            try:
                columns = json.loads(dataset.column_names_json)
                saved_mapping = json.loads(dataset.overview_mapping_json)
                if (
                    not isinstance(columns, list)
                    or not all(isinstance(c, str) for c in columns)
                    or not isinstance(saved_mapping, dict)
                    or not all(
                        isinstance(v, str) for v in saved_mapping.values()
                    )
                ):
                    raise ValueError(
                        "Saved source metadata is invalid. Re-save its column mapping in Data."
                    )
                mapping = UploadedData._validate_mapping(
                    columns, dataset.row_count, saved_mapping
                )
                result["coordinate_mode"] = mapping["coordinate_mode"]
                result["layers"] = [
                    {"key": key, "label": label, "column": mapping[key]}
                    for key, label in MEASUREMENTS.items()
                    if mapping[key]
                ]
                if mapping["coordinate_mode"] == "row_order":
                    OverviewGrid._check_positions(session, dataset.id)
                layer = (
                    preferred
                    if any(
                        item["key"] == preferred for item in result["layers"]
                    )
                    else result["layers"][0]["key"]
                    if result["layers"]
                    else ""
                )
                result["layer"], result["column"] = (
                    layer,
                    mapping.get(layer, ""),
                )
                query = (
                    select(
                        UploadedDatasetRow.row_position,
                        UploadedDatasetRow.cell_values_json,
                    )
                    .where(UploadedDatasetRow.dataset_id == dataset.id)
                    .order_by(
                        UploadedDatasetRow.row_position, UploadedDatasetRow.id
                    )
                    .limit(MAX_ROWS + 1)
                    .execution_options(yield_per=1000)
                )
                image, gradient = OverviewGrid._scan(
                    session.execute(query),
                    columns,
                    mapping,
                    layer,
                    result,
                    year if source_id == dataset.id else 0,
                    month if source_id == dataset.id else 0,
                )
            except ValueError as e:
                logging.exception(f"Error: {e}")
                result["status"], result["message"] = "error", str(e)
                return result
        if not result["layers"]:
            result["status"], result["message"] = (
                "unmapped",
                "Measurement not mapped. Configure columns in Data.",
            )
            return result
        if not result["total"]:
            result["status"], result["message"] = (
                "empty",
                "No saved rows in this source.",
            )
            return result
        if not result["periods"] and (
            result["dated_year"] or result["dated_month"]
        ):
            result["status"], result["message"] = (
                "empty",
                "No valid mapped dates. Year must be an integer 1–9999; month must be an integer 1–12. Rows with invalid mapped dates are excluded.",
            )
            return result
        if not result["period_rows"]:
            result["status"], result["message"] = (
                "empty",
                "No saved rows in the selected period. Select an available period.",
            )
            return result
        if not result["valid"]:
            result["status"] = "empty"
            result["message"] = (
                "All rows in the selected period have invalid pixel coordinates or malformed cells. Latitude/longitude are not pixel x/y. x must be integer 1–316 and y integer 1–332. Map valid pixel-coordinate columns in Data; row-order generation needs exactly 104,912 rows (332 × 316) with intact positions. No geographic conversion or automatic data changes are performed."
                if result["invalid_coordinates"] == result["period_rows"]
                else "The selected period has saved rows, but no valid readings for the selected mapped measurement. Empty or invalid cells remain transparent."
            )
            return result
        token = uuid4().hex
        filename, legend_filename = (
            f"overview_{token}.png",
            f"overview_{token}_legend.png",
        )
        try:
            directory = rx.get_upload_dir()
            directory.mkdir(parents=True, exist_ok=True)
            image.save(directory / filename, format="PNG", optimize=True)
            gradient.save(directory / legend_filename, format="PNG")
        except Exception as e:
            logging.exception(f"Error: {e}")
            OverviewGrid._remove_files([filename, legend_filename])
            raise
        result["filename"], result["legend_filename"] = (
            filename,
            legend_filename,
        )
        result["status"] = "ready"
        result["message"] = (
            "Saved CSV readings · selected period only · pixel positioning, no projection or inferred observations."
        )
        return result

    @staticmethod
    def _remove_files(filenames: list[str]):
        for filename in filenames:
            if filename:
                try:
                    (rx.get_upload_dir() / filename).unlink(missing_ok=True)
                except OSError as e:
                    logging.exception(f"Error: {e}")

    @rx.event
    def refresh(self):
        self.request_id += 1
        self.inspect_id += 1
        self.inspecting = False
        self.inspection_details = []
        self.inspection = (
            "Enter a pixel coordinate to inspect its saved observation."
        )
        self.status = "loading"
        self.metrics = []
        self.monthly = []
        self.chart_reason = "Loading saved observations…"
        self.message = (
            "Loading the saved source and rasterizing its mapped readings…"
        )
        return OverviewGrid.render(
            self.request_id,
            self.selected_layer,
            self.selected_year,
            self.selected_month,
            self.source_id,
        )

    @rx.event
    def choose_year(self, value: str):
        if value not in self.years or self.status == "loading":
            return
        self.playing = False
        self.play_id += 1
        self.selected_year = int(value)
        available = sorted(
            p["month"] for p in self.periods if p["year"] == self.selected_year
        )
        if self.selected_month not in available:
            self.selected_month = available[0]
        self.request_id += 1
        self.inspect_id += 1
        self.inspection_details = []
        return OverviewGrid.refresh

    @rx.event
    def choose_month(self, value: str):
        if value not in self.months or self.status == "loading":
            return
        self.playing = False
        self.play_id += 1
        self.selected_month = int(value)
        self.request_id += 1
        self.inspect_id += 1
        self.inspection_details = []
        return OverviewGrid.refresh

    @rx.event
    def step_month(self, amount: int):
        if (
            not self.dated_month
            or len(self.months) < 2
            or self.status == "loading"
        ):
            return
        months = [int(m) for m in self.months]
        self.selected_month = months[
            (months.index(self.selected_month) + amount) % len(months)
        ]
        self.request_id += 1
        self.inspect_id += 1
        self.inspection_details = []
        return OverviewGrid.refresh

    @rx.event
    def toggle_play(self):
        self.playing = (
            not self.playing and self.dated_month and len(self.months) > 1
        )
        self.play_id += 1
        if self.playing:
            return OverviewGrid.animate(self.play_id)

    @rx.event(background=True)
    async def animate(self, token: int):
        for _ in range(24):
            await asyncio.sleep(1.5)
            async with self:
                if not self.playing or token != self.play_id:
                    return
                ready = self.status != "loading"
            if ready:
                yield OverviewGrid.step_month(1)
        async with self:
            if token == self.play_id:
                self.playing = False

    @rx.event
    def choose_layer(self, key: str):
        if key not in {item["key"] for item in self.layers}:
            return
        self.selected_layer = key
        return OverviewGrid.refresh

    @rx.event(background=True)
    async def render(
        self,
        request_id: int,
        preferred: str,
        year: int = 0,
        month: int = 0,
        source_id: int = 0,
    ):
        try:
            result = await asyncio.to_thread(
                OverviewGrid._render, preferred, year, month, source_id
            )
            async with self:
                stale = request_id != self.request_id
                cleanup = (
                    [result["filename"], result["legend_filename"]]
                    if stale
                    else [self.filename, self.legend_filename]
                )
                if not stale:
                    if (
                        result["source_id"] != self.source_id
                        or not result["dated_month"]
                        or len(
                            {
                                p["month"]
                                for p in result["periods"]
                                if p["year"] == result["year"] and p["month"]
                            }
                        )
                        < 2
                    ):
                        self.playing = False
                        self.play_id += 1
                    self.periods = result["periods"]
                    self.selected_year, self.selected_month = (
                        result["year"],
                        result["month"],
                    )
                    self.dated_year, self.dated_month = (
                        result["dated_year"],
                        result["dated_month"],
                    )
                    self.year_source = result["year_source"]
                    self.month_source = result["month_source"]
                    self.invalid_dates, self.period_rows = (
                        result["invalid_dates"],
                        result["period_rows"],
                    )
                    self.metrics, self.monthly = (
                        result["metrics"],
                        result["monthly"],
                    )
                    self.chart_reason = result["chart_reason"]
                    self.status = result["status"]
                    self.source_id = result["source_id"]
                    self.source_name = result["name"]
                    self.selected_layer = result["layer"]
                    self.layers = result["layers"]
                    self.column = result["column"]
                    self.coordinate_mode = result["coordinate_mode"]
                    self.filename = result["filename"]
                    self.legend_filename = result["legend_filename"]
                    self.legends = result["legends"]
                    self.minimum, self.maximum = (
                        result["minimum"],
                        result["maximum"],
                    )
                    self.total, self.valid = result["total"], result["valid"]
                    self.invalid_coordinates = result["invalid_coordinates"]
                    self.duplicates = result["duplicates"]
                    self.invalid_readings = result["invalid_readings"]
                    self.message = result["message"]
                    self.updated = datetime.now(UTC).strftime(
                        "%d %b %Y · %H:%M:%S UTC"
                    )
            await asyncio.to_thread(OverviewGrid._remove_files, cleanup)
        except Exception as e:
            logging.exception(f"Error: {e}")
            async with self:
                if request_id == self.request_id:
                    self.status = "error"
                    self.message = "Could not read the saved source or generate its PNG. No demo observations are substituted. Refresh to retry."

    @staticmethod
    def _lookup(
        dataset_id: int,
        layer: str,
        x: int,
        y: int,
        year: int = 0,
        month: int = 0,
    ) -> tuple[str, list[dict[str, str]]]:
        with rx.session() as session:
            session.connection(
                execution_options={"isolation_level": "REPEATABLE READ"}
            )
            dataset = session.scalar(
                select(UploadedDataset)
                .where(
                    UploadedDataset.id == dataset_id,
                    UploadedDataset.overview_active.is_(True),
                )
                .limit(1)
            )
            if dataset is None:
                raise ValueError(
                    "The active source changed or was deleted. Refresh the Overview map."
                )
            columns = json.loads(dataset.column_names_json)
            mapping = UploadedData._validate_mapping(
                columns,
                dataset.row_count,
                json.loads(dataset.overview_mapping_json),
            )
            indices = OverviewGrid._indices(columns, mapping)
            query = (
                select(
                    UploadedDatasetRow.row_position,
                    UploadedDatasetRow.cell_values_json,
                )
                .where(UploadedDatasetRow.dataset_id == dataset_id)
                .order_by(
                    UploadedDatasetRow.row_position, UploadedDatasetRow.id
                )
            )
            if mapping["coordinate_mode"] == "row_order":
                OverviewGrid._check_positions(session, dataset_id)
                query = query.where(
                    UploadedDatasetRow.row_position == (332 - y) * 316 + x - 1
                ).limit(1)
            else:
                query = query.limit(MAX_ROWS + 1)
            found: list[str] | None = None
            matched = False
            for position, raw in session.execute(
                query.execution_options(yield_per=1000)
            ):
                cells = OverviewGrid._cells(raw, len(columns))
                if OverviewGrid._period(cells, indices, mapping) != (
                    year,
                    month,
                ):
                    continue
                if OverviewGrid._coordinate(
                    position, cells, indices, mapping["coordinate_mode"]
                ) == (x, y):
                    found, matched = cells, True
                    break
            if not matched:
                return f"No observation at that pixel · x={x}, y={y}.", []
            details: list[dict[str, str]] = []
            for key, label in MEASUREMENTS.items():
                if key not in indices:
                    continue
                raw_value = found[indices[key]] if found is not None else ""
                value = (
                    OverviewGrid._category(raw_value)
                    if key in DISCRETE
                    else OverviewGrid._number(raw_value)
                )
                display = (
                    value
                    if isinstance(value, str)
                    else f"{value:.6g}"
                    if value is not None
                    else "No valid reading (empty or invalid)"
                )
                selected = " · selected layer" if key == layer else ""
                details.append(
                    {
                        "label": f"{label} · {mapping[key]}{selected}",
                        "value": display,
                    }
                )
            for key, bound in (("latitude", 90), ("longitude", 180)):
                if key in indices:
                    value = (
                        OverviewGrid._number(found[indices[key]])
                        if found is not None
                        else None
                    )
                    display = (
                        f"{value:.6g}°"
                        if value is not None and abs(value) <= bound
                        else "Empty or invalid metadata"
                    )
                    details.append(
                        {
                            "label": f"{key.title()} · optional CSV metadata",
                            "value": display,
                        }
                    )
            observed_period = OverviewGrid._period(found, indices, mapping)
            for key, value in zip(("year", "month"), observed_period or (0, 0)):
                if value:
                    provenance = (
                        f"CSV column: {mapping[key]}"
                        if key in indices
                        else "Manual metadata for every row"
                    )
                    details.append(
                        {
                            "label": f"{key.title()} · {provenance}",
                            "value": str(value),
                        }
                    )
            heading = f"Saved observation at x={x}, y={y}."
            if layer not in indices:
                heading = f"Observation at x={x}, y={y} · selected measurement not mapped. Refresh the map."
            else:
                raw_value = found[indices[layer]] if found is not None else ""
                selected_value = (
                    OverviewGrid._category(raw_value)
                    if layer in DISCRETE
                    else OverviewGrid._number(raw_value)
                )
                if selected_value is None:
                    heading = f"Saved row at x={x}, y={y} · no valid reading for the selected layer."
            return heading, details

    @rx.event
    def inspect_pixel(self, form_data: dict[str, Any]):
        x, y = (
            self._number(form_data.get("x")),
            self._number(form_data.get("y")),
        )
        self.inspection_details = []
        if (
            x is None
            or y is None
            or not x.is_integer()
            or not y.is_integer()
            or not 1 <= x <= 316
            or not 1 <= y <= 332
        ):
            self.inspection = "Use integer x from 1–316 and y from 1–332."
            return
        if not self.source_id or self.status == "loading":
            self.inspection = "Wait for the active source to load, then retry."
            return
        self.inspect_id += 1
        self.inspecting = True
        self.inspection = "Looking up the saved pixel…"
        return OverviewGrid.lookup(
            self.inspect_id,
            self.request_id,
            self.source_id,
            self.selected_layer,
            int(x),
            int(y),
            self.selected_year,
            self.selected_month,
        )

    @rx.event(background=True)
    async def lookup(
        self,
        inspect_id: int,
        request_id: int,
        dataset_id: int,
        layer: str,
        x: int,
        y: int,
        year: int = 0,
        month: int = 0,
    ):
        try:
            heading, details = await asyncio.to_thread(
                OverviewGrid._lookup, dataset_id, layer, x, y, year, month
            )
            async with self:
                if (
                    inspect_id == self.inspect_id
                    and request_id == self.request_id
                    and year == self.selected_year
                    and month == self.selected_month
                ):
                    self.inspection, self.inspection_details = heading, details
                    self.inspecting = False
        except Exception as e:
            logging.exception(f"Error: {e}")
            async with self:
                if (
                    inspect_id == self.inspect_id
                    and request_id == self.request_id
                ):
                    self.inspection = (
                        str(e)
                        if isinstance(e, ValueError)
                        else "Could not look up this pixel. Refresh the map and retry."
                    )
                    self.inspecting = False
