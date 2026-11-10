import asyncio
import json
import logging
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import reflex as rx
from sqlalchemy import select

from antarctic_sea_ice_dashboard.models import (
    UploadedDataset,
    UploadedDatasetRow,
)
from antarctic_sea_ice_dashboard.states.antarctic_globe import (
    MEASUREMENT_FIELDS,
    AntarcticGlobe,
)
from antarctic_sea_ice_dashboard.states.uploaded_data import (
    DatasetSummary,
    MAX_ROWS,
    UploadedData,
)


class ComparisonResult(TypedDict):
    groups: list[dict[str, str]]
    period_a: str
    period_b: str
    measurements: list[dict[str, str]]
    measurement_key: str
    measurement_label: str
    measurement_units: str
    mean_a: str
    mean_b: str
    difference: str
    count_a: int
    count_b: int
    files_a: int
    files_b: int
    globe_filename: str
    comparable_cells: int
    globe_max_abs: float
    message: str


class SnapshotComparison(rx.State):
    groups: list[dict[str, str]] = []
    period_a: str = ""
    period_b: str = ""
    measurements: list[dict[str, str]] = []
    measurement_key: str = "sea_ice_concentration"
    measurement_label: str = ""
    measurement_units: str = ""
    mean_a: str = ""
    mean_b: str = ""
    difference: str = ""
    count_a: int = 0
    count_b: int = 0
    files_a: int = 0
    files_b: int = 0
    globe_filename: str = ""
    comparable_cells: int = 0
    globe_max_abs: float = 0
    message: str = "Choose two uploaded snapshots to compare."
    loading: bool = False
    error: bool = False
    request_id: int = 0

    @staticmethod
    def _format_mean(value: float | None, units: str) -> str:
        return "—" if value is None else f"{value:.4g} {units}"

    @staticmethod
    def _summarize_group(
        session,
        datasets: list[tuple[DatasetSummary, dict[str, str], list[str]]],
        measurement_key: str,
    ) -> tuple[
        float | None,
        int,
        int,
        dict[tuple[int, int], list[float]],
    ]:
        values: list[float] = []
        file_count = 0
        binned_values: dict[tuple[int, int], list[float]] = {}
        for summary, mapping, columns in datasets:
            column = mapping.get(measurement_key, "")
            if not column:
                continue
            file_count += 1
            indices = {
                "latitude": columns.index(mapping["latitude"]),
                "longitude": columns.index(mapping["longitude"]),
                "measurement": columns.index(column),
            }
            raw_values: list[float] = []
            located_values: list[tuple[int, int, float]] = []
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
            for position, (raw,) in enumerate(rows, start=1):
                if position > MAX_ROWS:
                    raise ValueError(
                        f"CSV layer {summary['name']} exceeds the supported {MAX_ROWS:,}-row limit."
                    )
                cells = AntarcticGlobe._cells(raw, len(columns))
                if cells is None:
                    continue
                latitude = AntarcticGlobe._number(cells[indices["latitude"]])
                longitude = AntarcticGlobe._number(cells[indices["longitude"]])
                if (
                    latitude is None
                    or longitude is None
                    or not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    continue
                value = AntarcticGlobe._number(cells[indices["measurement"]])
                if value is None or (
                    measurement_key == "sea_ice_concentration"
                    and not 0 <= value <= 100
                ):
                    continue
                raw_values.append(value)
                latitude_bin = min(359, int((latitude + 90) / 0.5))
                normalized_longitude = (longitude + 180) % 360
                longitude_bin = min(359, int(normalized_longitude))
                located_values.append((latitude_bin, longitude_bin, value))
            fraction = (
                measurement_key == "sea_ice_concentration"
                and bool(raw_values)
                and max(raw_values) <= 1
            )
            for latitude_bin, longitude_bin, value in located_values:
                normalized_value = value * 100 if fraction else value
                binned_values.setdefault(
                    (latitude_bin, longitude_bin), []
                ).append(normalized_value)
            if measurement_key == "sea_ice_concentration" and fraction:
                values.extend(value * 100 for value in raw_values)
            else:
                values.extend(raw_values)
        mean = sum(values) / len(values) if values else None
        return mean, len(values), file_count, binned_values

    @staticmethod
    def _compare(
        requested_a: str = "",
        requested_b: str = "",
        requested_measurement: str = "",
    ) -> ComparisonResult:
        with rx.session() as session:
            datasets = session.scalars(
                select(UploadedDataset)
                .where(UploadedDataset.source == "uploaded_csv")
                .order_by(
                    UploadedDataset.created_at.desc(),
                    UploadedDataset.id.desc(),
                )
            ).all()
            catalog: list[tuple[DatasetSummary, dict[str, str], list[str]]] = []
            for dataset in datasets:
                summary = UploadedData._dataset_summary(dataset)
                if not summary["map_ready"]:
                    continue
                catalog.append(
                    (
                        summary,
                        json.loads(dataset.map_mapping_json),
                        json.loads(dataset.column_names_json),
                    )
                )

            group_labels: dict[str, str] = {}
            for summary, _, _ in catalog:
                group_labels.setdefault(
                    summary["group_key"], summary["snapshot"]
                )
            keys = sorted(
                (key for key in group_labels if key != "undated"),
                reverse=True,
            )
            if "undated" in group_labels:
                keys.append("undated")
            groups = [{"key": key, "label": group_labels[key]} for key in keys]
            period_a = (
                requested_a
                if requested_a in group_labels
                else (keys[0] if keys else "")
            )
            period_b = (
                requested_b
                if requested_b in group_labels
                else (keys[1] if len(keys) > 1 else "")
            )
            rows_a = [
                item for item in catalog if item[0]["group_key"] == period_a
            ]
            rows_b = [
                item for item in catalog if item[0]["group_key"] == period_b
            ]
            available_a = {
                key
                for key, _, _ in MEASUREMENT_FIELDS
                if any(mapping.get(key) for _, mapping, _ in rows_a)
            }
            available_b = {
                key
                for key, _, _ in MEASUREMENT_FIELDS
                if any(mapping.get(key) for _, mapping, _ in rows_b)
            }
            common = available_a & available_b if period_b else available_a
            measurements = [
                {"key": key, "label": label, "units": units}
                for key, label, units in MEASUREMENT_FIELDS
                if key in common
            ]
            selected_key = (
                requested_measurement
                if requested_measurement in common
                else (
                    "sea_ice_concentration"
                    if "sea_ice_concentration" in common
                    else (measurements[0]["key"] if measurements else "")
                )
            )
            selected = next(
                (item for item in measurements if item["key"] == selected_key),
                {"key": "", "label": "", "units": ""},
            )
            result: ComparisonResult = {
                "groups": groups,
                "period_a": period_a,
                "period_b": period_b,
                "measurements": measurements,
                "measurement_key": selected["key"],
                "measurement_label": selected["label"],
                "measurement_units": selected["units"],
                "mean_a": "",
                "mean_b": "",
                "difference": "",
                "count_a": 0,
                "count_b": 0,
                "files_a": 0,
                "files_b": 0,
                "globe_filename": "",
                "comparable_cells": 0,
                "globe_max_abs": 0,
                "message": "",
            }
            if not period_a or not period_b:
                result["message"] = (
                    "Map at least two uploaded Year/Month snapshots to compare them."
                )
                return result
            if not selected_key:
                result["message"] = (
                    "The selected snapshots have no shared mapped measurement."
                )
                return result

            mean_a, count_a, files_a, bins_a = (
                SnapshotComparison._summarize_group(
                    session, rows_a, selected_key
                )
            )
            mean_b, count_b, files_b, bins_b = (
                SnapshotComparison._summarize_group(
                    session, rows_b, selected_key
                )
            )
            result["mean_a"] = SnapshotComparison._format_mean(
                mean_a, selected["units"]
            )
            result["mean_b"] = SnapshotComparison._format_mean(
                mean_b, selected["units"]
            )
            result["count_a"] = count_a
            result["count_b"] = count_b
            result["files_a"] = files_a
            result["files_b"] = files_b
            comparison_points: list[list[str | float | int]] = []
            for cell in sorted(bins_a.keys() & bins_b.keys()):
                values_a = bins_a[cell]
                values_b = bins_b[cell]
                average_a = sum(values_a) / len(values_a)
                average_b = sum(values_b) / len(values_b)
                delta = average_b - average_a
                comparison_points.append(
                    [
                        -179.5 + cell[1],
                        -89.75 + cell[0] * 0.5,
                        delta,
                        average_a,
                        average_b,
                        len(values_a),
                        len(values_b),
                        selected["units"],
                    ]
                )
            if comparison_points:
                max_abs = max(
                    abs(float(point[2])) for point in comparison_points
                )
                filename = f"antarctic_comparison_{uuid4().hex}.json"
                path: Path = rx.get_upload_dir() / filename
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("w", encoding="utf-8") as file:
                        json.dump(
                            {
                                "points": comparison_points,
                                "color_mode": "difference",
                                "max_abs": max_abs,
                                "cell_size": "0.5° latitude × 1° longitude",
                            },
                            file,
                            separators=(",", ":"),
                        )
                except Exception:
                    logging.exception(
                        "Could not write comparison globe point data."
                    )
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        logging.exception(
                            "Could not remove partial comparison globe data."
                        )
                    raise
                result["globe_filename"] = filename
                result["comparable_cells"] = len(comparison_points)
                result["globe_max_abs"] = max_abs
            if mean_a is None or mean_b is None:
                result["difference"] = "—"
                result["message"] = (
                    "At least one snapshot has no valid readings for this measurement."
                )
            elif not comparison_points:
                result["message"] = (
                    "Snapshot means are available, but no 0.5° × 1° geographic cells contain valid readings in both snapshots; no difference globe can be drawn."
                )
            else:
                delta = mean_b - mean_a
                result["difference"] = f"{delta:+.4g} {selected['units']}"
                result["message"] = (
                    f"Difference is second snapshot minus first: "
                    f"{group_labels[period_b]} − {group_labels[period_a]}."
                )
            return result

    @rx.event
    def refresh(self):
        return self._start_comparison()

    @staticmethod
    def _remove_file(filename: str):
        if not filename:
            return
        try:
            (rx.get_upload_dir() / filename).unlink(missing_ok=True)
        except OSError:
            logging.exception("Could not remove stale comparison globe data.")

    @rx.event
    def select_period_a(self, value: str):
        if value not in {group["key"] for group in self.groups}:
            return
        self.period_a = value
        return self._start_comparison()

    @rx.event
    def select_period_b(self, value: str):
        if value and value not in {group["key"] for group in self.groups}:
            return
        self.period_b = value
        return self._start_comparison()

    @rx.event
    def select_measurement(self, value: str):
        if value not in {item["key"] for item in self.measurements}:
            return
        self.measurement_key = value
        return self._start_comparison()

    def _start_comparison(self):
        self.request_id += 1
        self.loading = True
        self.error = False
        self.message = "Calculating snapshot summaries…"
        return SnapshotComparison.calculate(
            self.request_id,
            self.period_a,
            self.period_b,
            self.measurement_key,
        )

    @rx.event(background=True)
    async def calculate(
        self,
        request_id: int,
        period_a: str,
        period_b: str,
        measurement_key: str,
    ):
        try:
            result = await asyncio.to_thread(
                SnapshotComparison._compare,
                period_a,
                period_b,
                measurement_key,
            )
            previous = ""
            async with self:
                stale = request_id != self.request_id
                previous = self.globe_filename
                if not stale:
                    self.groups = result["groups"]
                    self.period_a = result["period_a"]
                    self.period_b = result["period_b"]
                    self.measurements = result["measurements"]
                    self.measurement_key = result["measurement_key"]
                    self.measurement_label = result["measurement_label"]
                    self.measurement_units = result["measurement_units"]
                    self.mean_a = result["mean_a"]
                    self.mean_b = result["mean_b"]
                    self.difference = result["difference"]
                    self.count_a = result["count_a"]
                    self.count_b = result["count_b"]
                    self.files_a = result["files_a"]
                    self.files_b = result["files_b"]
                    self.globe_filename = result["globe_filename"]
                    self.comparable_cells = result["comparable_cells"]
                    self.globe_max_abs = result["globe_max_abs"]
                    self.message = result["message"]
                    self.loading = False
                    self.error = False
            await asyncio.to_thread(
                SnapshotComparison._remove_file,
                result["globe_filename"] if stale else previous,
            )
        except Exception as error:
            logging.exception("Could not compare uploaded snapshots.")
            previous = ""
            async with self:
                if request_id == self.request_id:
                    previous = self.globe_filename
                    self.message = (
                        str(error)
                        if isinstance(error, ValueError)
                        else "Could not read the mapped CSV snapshots. Refresh and retry."
                    )
                    self.loading = False
                    self.error = True
                    self.mean_a = ""
                    self.mean_b = ""
                    self.difference = ""
                    self.count_a = 0
                    self.count_b = 0
                    self.files_a = 0
                    self.files_b = 0
                    self.globe_filename = ""
                    self.comparable_cells = 0
                    self.globe_max_abs = 0
            await asyncio.to_thread(SnapshotComparison._remove_file, previous)
