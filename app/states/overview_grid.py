import reflex as rx
import asyncio
import base64
import colorsys
import io
import json
import logging
import math
from array import array
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import uuid4

from PIL import Image
from sqlalchemy import func, select
from app.models import UploadedDataset, UploadedDatasetRow
from app.states.uploaded_data import GRID_ROWS, MAX_ROWS, UploadedData


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


class GridLayer(TypedDict):
    key: str
    label: str
    column: str


class GridLegend(TypedDict):
    label: str
    swatch: str


class GridResult(TypedDict):
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
        try:
            number = float(value)
        except (ValueError, OverflowError):
            logging.exception("Unexpected error")
            return None
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
            if key != "coordinate_mode" and value
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
            raw_value = cells[indices[layer]] if cells is not None else ""
            value = OverviewGrid._number(raw_value)
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
    def _continuous_color(fraction: float) -> tuple[int, int, int]:
        fraction = min(1.0, max(0.0, fraction))
        return tuple(
            round(start + (end - start) * fraction)
            for start, end in zip((225, 245, 250), (15, 76, 112))
        )

    @staticmethod
    def _render(preferred: str) -> GridResult:
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
                if not result["layers"]:
                    result["status"] = "unmapped"
                    result["message"] = (
                        "Measurement not mapped. Open Data and map at least one measurement to render this source."
                    )
                    return result
                layer = (
                    preferred
                    if any(
                        item["key"] == preferred for item in result["layers"]
                    )
                    else result["layers"][0]["key"]
                )
                result["layer"], result["column"] = layer, mapping[layer]
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
                image, gradient = OverviewGrid._raster(
                    session.execute(query), columns, mapping, layer, result
                )
            except ValueError as e:
                logging.exception(f"Error: {e}")
                result["status"], result["message"] = "error", str(e)
                return result
        if not result["valid"]:
            result["status"] = "empty"
            result["message"] = (
                "No valid readings for the selected mapped measurement. Empty or invalid cells remain transparent."
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
            "Saved CSV readings · pixel positioning only · no projection or inferred observations."
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
        self.message = (
            "Loading the saved source and rasterizing its mapped readings…"
        )
        return OverviewGrid.render(self.request_id, self.selected_layer)

    @rx.event
    def choose_layer(self, key: str):
        if key not in {item["key"] for item in self.layers}:
            return
        self.selected_layer = key
        return OverviewGrid.refresh

    @rx.event(background=True)
    async def render(self, request_id: int, preferred: str):
        try:
            result = await asyncio.to_thread(OverviewGrid._render, preferred)
            async with self:
                stale = request_id != self.request_id
                cleanup = (
                    [result["filename"], result["legend_filename"]]
                    if stale
                    else [self.filename, self.legend_filename]
                )
                if not stale:
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
        dataset_id: int, layer: str, x: int, y: int
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
    ):
        try:
            heading, details = await asyncio.to_thread(
                OverviewGrid._lookup, dataset_id, layer, x, y
            )
            async with self:
                if (
                    inspect_id == self.inspect_id
                    and request_id == self.request_id
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
