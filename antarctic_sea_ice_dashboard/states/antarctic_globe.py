import asyncio
import json
import logging
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import reflex as rx
from sqlalchemy import select

from antarctic_sea_ice_dashboard.models import UploadedDataset, UploadedDatasetRow
from antarctic_sea_ice_dashboard.states.uploaded_data import (
    DatasetSummary,
    UploadedData,
)


MEASUREMENT_FIELDS = (
    ("sea_ice_concentration", "Sea ice concentration", "%"),
    ("sea_surface_temperature", "Sea-surface temperature", "°C"),
    ("wind_speed", "Wind speed", "m/s"),
    ("air_temperature", "Air temperature", "°C"),
)
MEASUREMENT_LABELS = {
    key: (label, units) for key, label, units in MEASUREMENT_FIELDS
}
MAX_ROWS = 120000


class GlobeResult(TypedDict):
    status: str
    filename: str
    groups: list[dict[str, str]]
    selected_group: str
    layers: list[DatasetSummary]
    source_name: str
    measurements: list[dict[str, str]]
    measurement_key: str
    measurement_label: str
    measurement_column: str
    measurement_units: str
    value_range: str
    snapshot_label: str
    total: int
    valid: int
    invalid_coordinates: int
    invalid_readings: int
    average: str
    message: str


class AntarcticGlobe(rx.State):
    status: str = "loading"
    filename: str = ""
    groups: list[dict[str, str]] = []
    selected_group: str = ""
    layers: list[DatasetSummary] = []
    source_name: str = ""
    measurements: list[dict[str, str]] = []
    measurement_key: str = "sea_ice_concentration"
    measurement_label: str = ""
    measurement_column: str = ""
    measurement_units: str = ""
    value_range: str = ""
    snapshot_label: str = ""
    total: int = 0
    valid: int = 0
    invalid_coordinates: int = 0
    invalid_readings: int = 0
    average: str = ""
    message: str = "Loading geographic observations…"
    updated: str = ""
    request_id: int = 0

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            number = float(value.strip().replace(",", ""))
        except (AttributeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _cells(raw: str, column_count: int) -> list[str] | None:
        try:
            cells = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if (
            not isinstance(cells, list)
            or len(cells) != column_count
            or not all(isinstance(cell, str) for cell in cells)
        ):
            return None
        return cells

    @staticmethod
    def _snapshot(mapping: dict[str, str]) -> tuple[str, str]:
        year, month = mapping.get("fixed_year", ""), mapping.get(
            "fixed_month", ""
        )
        if bool(year) != bool(month):
            raise ValueError("Both snapshot year and month are required.")
        if not year:
            return "undated", "Undated"
        if not re.fullmatch(r"[0-9]{1,4}", year) or not re.fullmatch(
            r"(?:[1-9]|1[0-2])", month
        ):
            raise ValueError("Saved snapshot date metadata is invalid.")
        key = f"{int(year):04d}-{int(month):02d}"
        return key, key

    @staticmethod
    def _render(
        selected_group: str = "",
        measurement_key: str = "sea_ice_concentration",
    ) -> GlobeResult:
        with rx.session() as session:
            datasets = session.scalars(
                select(UploadedDataset)
                .where(UploadedDataset.source == "uploaded_csv")
                .order_by(
                    UploadedDataset.created_at.desc(),
                    UploadedDataset.id.desc(),
                )
            ).all()
            catalogue: list[tuple[DatasetSummary, dict[str, str], list[str]]] = []
            for dataset in datasets:
                try:
                    summary = UploadedData._dataset_summary(dataset)
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    logging.exception("Could not read uploaded CSV mapping.")
                    continue
                if not summary["map_ready"]:
                    continue
                mapping = json.loads(dataset.map_mapping_json)
                columns = json.loads(dataset.column_names_json)
                catalogue.append((summary, mapping, columns))

            group_entries: dict[str, str] = {}
            for summary, _, _ in catalogue:
                group_entries.setdefault(
                    summary["group_key"], summary["snapshot"]
                )
            ordered_groups = sorted(
                (key for key in group_entries if key != "undated"),
                reverse=True,
            )
            if "undated" in group_entries:
                ordered_groups.append("undated")
            groups = [
                {"key": key, "label": group_entries[key]}
                for key in ordered_groups
            ]
            selected = (
                selected_group
                if selected_group in group_entries
                else (groups[0]["key"] if groups else "")
            )
            selected_rows = [
                item
                for item in catalogue
                if item[0]["group_key"] == selected
            ]
            layers = [item[0] for item in selected_rows]
            measurements = [
                {"key": key, "label": label, "units": units}
                for key, label, units in MEASUREMENT_FIELDS
                if any(
                    summary["active"] and mapping.get(key)
                    for summary, mapping, _ in selected_rows
                )
            ]
            available_keys = {item["key"] for item in measurements}
            if measurement_key not in available_keys and measurements:
                measurement_key = measurements[0]["key"]
            selected_measurement = next(
                (
                    item
                    for item in measurements
                    if item["key"] == measurement_key
                ),
                {"key": "", "label": "", "units": ""},
            )

            result: GlobeResult = {
                "status": "demo" if not any(layer["active"] for layer in layers) else "empty",
                "filename": "",
                "groups": groups,
                "selected_group": selected,
                "layers": layers,
                "source_name": ", ".join(
                    layer["name"] for layer in layers if layer["active"]
                ),
                "measurements": measurements,
                "measurement_key": selected_measurement["key"],
                "measurement_label": selected_measurement["label"],
                "measurement_column": "",
                "measurement_units": selected_measurement["units"],
                "value_range": "",
                "snapshot_label": group_entries.get(selected, "No dated CSV group"),
                "total": 0,
                "valid": 0,
                "invalid_coordinates": 0,
                "invalid_readings": 0,
                "average": "",
                "message": "",
            }
            if not selected or not selected_measurement["key"]:
                result["message"] = (
                    "Apply a geographic CSV layer with a supported measurement in Data."
                    if not groups
                    else "No supported measurements are mapped for this snapshot."
                )

            points: list[list[str | float]] = []
            all_values: list[float] = []
            mapped_columns: list[str] = []
            active_layers = [
                item for item in selected_rows if item[0]["active"]
            ]
            for summary, mapping, columns in active_layers:
                measurement_column = mapping.get(measurement_key, "")
                if not measurement_column:
                    continue
                indices = {
                    field: columns.index(mapping[field])
                    for field in ("latitude", "longitude", measurement_key)
                }
                mapped_columns.append(measurement_column)
                values_for_layer: list[float] = []
                raw_points: list[tuple[float, float, float]] = []
                rows = session.execute(
                    select(UploadedDatasetRow.cell_values_json)
                    .where(UploadedDatasetRow.dataset_id == summary["id"])
                    .order_by(
                        UploadedDatasetRow.row_position,
                        UploadedDatasetRow.id,
                    )
                    .limit(MAX_ROWS + 1)
                    .execution_options(yield_per=1000)
                )
                layer_rows = 0
                for (raw,) in rows:
                    result["total"] += 1
                    layer_rows += 1
                    if layer_rows > MAX_ROWS:
                        raise ValueError(
                            f"CSV layer {summary['name']} exceeds the supported 120,000-row limit."
                        )
                    cells = AntarcticGlobe._cells(raw, len(columns))
                    if cells is None:
                        result["invalid_coordinates"] += 1
                        continue
                    latitude = AntarcticGlobe._number(cells[indices["latitude"]])
                    longitude = AntarcticGlobe._number(
                        cells[indices["longitude"]]
                    )
                    if (
                        latitude is None
                        or longitude is None
                        or not -90 <= latitude <= 90
                        or not -180 <= longitude <= 180
                    ):
                        result["invalid_coordinates"] += 1
                        continue
                    value = AntarcticGlobe._number(
                        cells[indices[measurement_key]]
                    )
                    if value is None or (
                        measurement_key == "sea_ice_concentration"
                        and not 0 <= value <= 100
                    ):
                        result["invalid_readings"] += 1
                        continue
                    raw_points.append((longitude, latitude, value))
                    values_for_layer.append(value)
                fractional = (
                    measurement_key == "sea_ice_concentration"
                    and bool(values_for_layer)
                    and max(values_for_layer) <= 1
                )
                for longitude, latitude, raw_value in raw_points:
                    value = raw_value * 100 if fractional else raw_value
                    points.append(
                        [
                            longitude,
                            latitude,
                            value,
                            value,
                            summary["name"],
                            measurement_column,
                            selected_measurement["units"],
                        ]
                    )
                    all_values.append(value)

            if measurement_key != "sea_ice_concentration" and all_values:
                minimum, maximum = min(all_values), max(all_values)
                span = maximum - minimum
                for point in points:
                    point[2] = (
                        50
                        if span == 0
                        else (float(point[3]) - minimum) / span * 100
                    )
                result["value_range"] = (
                    f"{minimum:.3g}–{maximum:.3g} {selected_measurement['units']}"
                )
            elif measurement_key == "sea_ice_concentration":
                result["value_range"] = "0–100%"
            else:
                result["value_range"] = (
                    f"No valid {selected_measurement['units']} values"
                )
            if all_values:
                result["average"] = (
                    f"{sum(all_values) / len(all_values):.3g} "
                    f"{selected_measurement['units']}"
                )
            result["measurement_column"] = (
                ", ".join(dict.fromkeys(mapped_columns))
                if mapped_columns
                else "Not mapped in active layers"
            )
            result["valid"] = len(points)

        filename = f"antarctic_globe_{uuid4().hex}.json"
        path: Path = rx.get_upload_dir() / filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as file:
                json.dump({"points": points}, file, separators=(",", ":"))
        except Exception:
            logging.exception("Could not write the Antarctic globe point data.")
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.exception("Could not remove a partial globe data file.")
            raise

        result["filename"] = filename
        result["status"] = "ready" if points else (
            "empty" if active_layers else "demo"
        )
        result["message"] = (
            f"{result['valid']:,} valid observations across "
            f"{len(active_layers)} active CSV layer(s)."
        )
        return result

    @staticmethod
    def _remove_file(filename: str):
        if not filename:
            return
        try:
            (rx.get_upload_dir() / filename).unlink(missing_ok=True)
        except OSError:
            logging.exception("Could not remove a generated globe data file.")

    @rx.event
    def refresh(self):
        self.request_id += 1
        self.status = "loading"
        self.message = "Loading geographic observations…"
        return AntarcticGlobe.render(
            self.request_id, self.selected_group, self.measurement_key
        )

    @rx.event
    def select_group(self, value: str):
        if value not in {group["key"] for group in self.groups}:
            return
        self.selected_group = value
        self.request_id += 1
        self.status = "loading"
        self.message = "Loading the selected snapshot…"
        return AntarcticGlobe.render(
            self.request_id, value, self.measurement_key
        )

    @rx.event
    def select_measurement(self, value: str):
        if value not in {item["key"] for item in self.measurements}:
            return
        self.measurement_key = value
        self.request_id += 1
        self.status = "loading"
        self.message = "Updating the globe measurement…"
        return AntarcticGlobe.render(
            self.request_id, self.selected_group, value
        )

    @rx.event(background=True)
    async def toggle_layer(self, dataset_id: int):
        layer = next(
            (item for item in self.layers if item["id"] == dataset_id), None
        )
        if layer is None:
            return
        self.request_id += 1
        request_id = self.request_id
        self.status = "loading"
        try:
            await asyncio.to_thread(
                UploadedData._set_layer_active, dataset_id, not layer["active"]
            )
            async with self:
                self.message = "Updating active CSV layers…"
                selected_group = self.selected_group
                measurement_key = self.measurement_key
            yield UploadedData.load_catalogue
            yield AntarcticGlobe.render(
                request_id, selected_group, measurement_key
            )
        except Exception as error:
            logging.exception("Could not update the active CSV layer.")
            async with self:
                if request_id == self.request_id:
                    self.status = "error"
                    self.message = (
                        str(error)
                        if isinstance(error, ValueError)
                        else "Could not update the active CSV layer. Refresh and retry."
                    )

    @rx.event(background=True)
    async def render(
        self, request_id: int, selected_group: str, measurement_key: str
    ):
        previous = ""
        try:
            result = await asyncio.to_thread(
                AntarcticGlobe._render, selected_group, measurement_key
            )
            async with self:
                stale = request_id != self.request_id
                previous = self.filename
                if not stale:
                    self.status = result["status"]
                    self.filename = result["filename"]
                    self.groups = result["groups"]
                    self.selected_group = result["selected_group"]
                    self.layers = result["layers"]
                    self.source_name = result["source_name"]
                    self.measurements = result["measurements"]
                    self.measurement_key = result["measurement_key"]
                    self.measurement_label = result["measurement_label"]
                    self.measurement_column = result["measurement_column"]
                    self.measurement_units = result["measurement_units"]
                    self.value_range = result["value_range"]
                    self.snapshot_label = result["snapshot_label"]
                    self.total = result["total"]
                    self.valid = result["valid"]
                    self.invalid_coordinates = result["invalid_coordinates"]
                    self.invalid_readings = result["invalid_readings"]
                    self.average = result["average"]
                    self.message = result["message"]
                    self.updated = datetime.now(UTC).strftime(
                        "%d %b %Y · %H:%M:%S UTC"
                    )
            await asyncio.to_thread(
                AntarcticGlobe._remove_file,
                result["filename"] if stale else previous,
            )
        except Exception as error:
            logging.exception("Could not render the Antarctic globe.")
            async with self:
                if request_id == self.request_id:
                    previous = self.filename
                    self.filename = ""
                    self.status = "error"
                    self.message = (
                        str(error)
                        if isinstance(error, ValueError)
                        else "Could not read the saved sources or generate globe data. Refresh to retry."
                    )
            await asyncio.to_thread(AntarcticGlobe._remove_file, previous)
