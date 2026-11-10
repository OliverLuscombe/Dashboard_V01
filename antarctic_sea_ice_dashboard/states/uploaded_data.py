import reflex as rx
import asyncio
import csv
import io
import json
import logging
import re
from uuid import uuid4
from pathlib import PurePath
from typing import Any, TypedDict

from sqlalchemy import delete, func, insert, select, text
from antarctic_sea_ice_dashboard.models import UploadedDataset, UploadedDatasetRow


MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 120000
MAX_COLUMNS = 10
MAX_CELL = 32768
PAGE_SIZE = 25
MAPPING_LABELS: dict[str, str] = {
    "latitude": "Latitude",
    "longitude": "Longitude",
    "sea_ice_concentration": "Sea ice concentration (%)",
    "sea_surface_temperature": "Sea-surface temperature (°C)",
    "wind_speed": "Wind speed (m/s)",
    "air_temperature": "Air temperature (°C)",
}


class MappingField(TypedDict):
    name: str
    label: str
    value: str


class DatasetSummary(TypedDict):
    id: int
    name: str
    filename: str
    rows: int
    columns: int
    created: str
    active: bool
    map_ready: bool
    snapshot: str
    group_key: str
    map_message: str


class PreviewRow(TypedDict):
    id: int
    number: int
    cells: list[str]


class EditorField(TypedDict):
    name: str
    label: str
    value: str


class UploadedData(rx.State):
    catalogue: list[DatasetSummary] = []
    selected_id: int = 0
    selected_name: str = ""
    original_filename: str = ""
    columns: list[str] = []
    rows: list[PreviewRow] = []
    row_count: int = 0
    page_index: int = 0
    loading: bool = False
    importing: bool = False
    upload_year: str = ""
    upload_month: str = ""
    error: str = ""
    success: str = ""
    editor_mode: str = ""
    editor_row_id: int = 0
    editor_row_number: int = 0
    editor_original: str = ""
    editor_fields: list[EditorField] = []
    form_revision: int = 0
    rename_open: bool = False
    confirmation: str = ""
    active_sources: list[DatasetSummary] = []
    mapping_fields: list[MappingField] = []
    fixed_year: str = ""
    fixed_month: str = ""
    selected_source_active: bool = False
    source_error: str = ""
    source_success: str = ""
    source_saving: bool = False
    mapping_revision: int = 0

    @rx.var
    def page_count(self) -> int:
        return max(1, (self.row_count + PAGE_SIZE - 1) // PAGE_SIZE)

    @rx.var
    def range_label(self) -> str:
        if not self.row_count:
            return "0 rows"
        start = self.page_index * PAGE_SIZE + 1
        end = min(self.row_count, start + PAGE_SIZE - 1)
        return f"Rows {start}–{end} of {self.row_count:,}"

    @staticmethod
    def _suggest_mapping(columns: list[str]) -> dict[str, str]:
        aliases: dict[str, list[str]] = {
            "latitude": ["latitude", "lat", "latitudedegrees"],
            "longitude": ["longitude", "lon", "long", "longitudedegrees"],
            "sea_ice_concentration": [
                "concentration",
                "seaiceconcentration",
                "seaiceconcentrationpercent",
                "seaiceconcentrationpct",
                "sic",
                "iceconcentration",
            ],
            "sea_surface_temperature": [
                "seasurfacetemperature",
                "seasurfacetemperaturec",
                "sst",
                "sstc",
            ],
            "wind_speed": ["windspeed", "windspeedms", "wind", "windms"],
            "air_temperature": [
                "airtemperature",
                "airtemperaturec",
                "airt",
                "airtempc",
            ],
        }
        normalized = [
            (re.sub(r"[^a-z0-9]", "", column.casefold()), column)
            for column in columns
        ]
        return {
            field: next(
                (column for key, column in normalized if key in aliases[field]),
                "",
            )
            for field in MAPPING_LABELS
        }

    @staticmethod
    def _duplicate_mapping_error(mapping: dict[str, str]) -> str:
        seen: dict[str, str] = {}
        for field, label in MAPPING_LABELS.items():
            column = mapping.get(field, "")
            if not column:
                continue
            if column in seen:
                first = seen[column]
                remedy = "Change one field to Not provided (if absent), or choose another distinct CSV column."
                return (
                    f'CSV column "{column}" is selected for both "{MAPPING_LABELS[first]}" and "{label}". '
                    f"Map each source column to only one active field. {remedy} No changes were saved."
                )
            seen[column] = field
        return ""

    @staticmethod
    def _fixed_dates(mapping: dict[str, str]) -> dict[str, str]:
        clean: dict[str, str] = {}
        for key, bound in (("year", 9999), ("month", 12)):
            raw = mapping.get(f"fixed_{key}", "")
            if not isinstance(raw, str):
                raise ValueError(
                    f"{key.title()} for every row must be a whole-number text value from 1–{bound}, or blank. No changes were saved."
                )
            raw = raw.strip()
            digits = raw.lstrip("0") or "0"
            if raw and (
                not re.fullmatch(r"[0-9]+", raw)
                or len(digits) > len(str(bound))
                or not 1 <= int(digits) <= bound
            ):
                raise ValueError(
                    f"{key.title()} for every row must be an integer from 1–{bound}, or blank. Remove decimals, signs or month names and enter a whole number. No changes were saved."
                )
            clean[f"fixed_{key}"] = str(int(digits)) if raw else ""
        return clean

    @staticmethod
    def _validate_mapping(
        columns: list[str], _row_count: int, mapping: dict[str, str]
    ) -> dict[str, str]:
        fixed = UploadedData._fixed_dates(mapping)
        if bool(fixed["fixed_year"]) != bool(fixed["fixed_month"]):
            raise ValueError(
                "Enter both snapshot year and month, or leave both blank for an undated CSV."
            )
        clean = {field: mapping.get(field, "") for field in MAPPING_LABELS}
        if any(value and value not in columns for value in clean.values()):
            raise ValueError(
                "A mapped column is no longer available. Refresh the catalogue and retry."
            )
        if not clean["latitude"] or not clean["longitude"]:
            raise ValueError(
                "Map Latitude and Longitude columns to position observations on the globe."
            )
        if not any(
            clean[key]
            for key in (
                "sea_ice_concentration",
                "sea_surface_temperature",
                "wind_speed",
                "air_temperature",
            )
        ):
            raise ValueError(
                "Map at least one supported measurement column for the globe."
            )
        duplicate_error = UploadedData._duplicate_mapping_error(mapping)
        if duplicate_error:
            raise ValueError(duplicate_error)
        clean.update(fixed)
        return clean

    @staticmethod
    def _parse_csv(
        filename: str, data: bytes
    ) -> tuple[list[str], list[list[str]]]:
        if PurePath(filename).suffix.lower() != ".csv":
            raise ValueError("Choose a file with a .csv extension.")
        if len(data) > MAX_BYTES:
            raise ValueError("This CSV exceeds the 20 MB per-file limit.")
        if not data:
            raise ValueError("The file is empty. Include a header row.")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            logging.exception(f"Error: {type(e).__name__}")
            raise ValueError(
                "Use UTF-8 or UTF-8 with BOM encoding; this file could not be decoded."
            ) from e
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        try:
            headers = next(reader, [])
            if not headers or any(not name.strip() for name in headers):
                raise ValueError(
                    "Every column needs a nonempty header in the first row."
                )
            if len(headers) > MAX_COLUMNS:
                raise ValueError("Use at most 10 columns per CSV.")
            if len(set(name.strip() for name in headers)) != len(headers):
                raise ValueError(
                    "Column headers must be unique, including after trimming whitespace."
                )
            if any(len(name) > MAX_CELL for name in headers):
                raise ValueError(
                    "A header is too long. Limit each header to 32,768 characters."
                )
            records: list[list[str]] = []
            for index, cells in enumerate(reader, start=1):
                if index > MAX_ROWS:
                    raise ValueError("Use at most 120,000 data rows per CSV.")
                if len(cells) != len(headers):
                    raise ValueError(
                        f"Data row {index} has {len(cells)} fields; expected {len(headers)}. Check blank lines, commas and quoting."
                    )
                if any(len(cell) > MAX_CELL for cell in cells):
                    raise ValueError(
                        f"Data row {index} contains a cell exceeding 32,768 characters."
                    )
                records.append(cells)
            return headers, records
        except csv.Error as e:
            logging.exception(f"Error: {type(e).__name__}")
            raise ValueError(
                f"Invalid CSV quoting or an oversized field near file line {reader.line_num}."
            ) from e

    @staticmethod
    def _dataset_summary(dataset: UploadedDataset) -> DatasetSummary:
        columns = json.loads(dataset.column_names_json)
        saved_mapping = json.loads(dataset.map_mapping_json)
        if (
            not isinstance(columns, list)
            or not all(isinstance(column, str) for column in columns)
            or not isinstance(saved_mapping, dict)
            or not all(isinstance(value, str) for value in saved_mapping.values())
        ):
            raise ValueError(
                f"Saved mapping for {dataset.name} is invalid. Review it in Data."
            )
        snapshot = "Undated"
        group_key = "undated"
        map_ready = False
        map_message = "Map Latitude, Longitude, and a supported measurement in Data."
        try:
            UploadedData._validate_mapping(
                columns, dataset.row_count, saved_mapping
            )
            dates = UploadedData._fixed_dates(saved_mapping)
            year, month = dates["fixed_year"], dates["fixed_month"]
            if bool(year) != bool(month):
                raise ValueError("Both snapshot year and month are required.")
            if year and month:
                group_key = f"{int(year):04d}-{int(month):02d}"
                snapshot = group_key
            map_ready = True
            map_message = ""
        except ValueError as error:
            map_message = str(error)
        return {
            "id": dataset.id,
            "name": dataset.name,
            "filename": dataset.original_filename,
            "rows": dataset.row_count,
            "columns": len(columns),
            "created": dataset.created_at.strftime("%d %b %Y · %H:%M UTC"),
            "active": dataset.map_layer_active,
            "map_ready": map_ready,
            "snapshot": snapshot,
            "group_key": group_key,
            "map_message": map_message,
        }

    def _clear_editor(self):
        self.editor_mode = ""
        self.editor_row_id = 0
        self.editor_row_number = 0
        self.editor_original = ""
        self.editor_fields = []
        self.confirmation = ""
        self.form_revision += 1

    def _clear_selection(self):
        self.selected_id = 0
        self.selected_name = ""
        self.original_filename = ""
        self.columns = []
        self.rows = []
        self.row_count = 0
        self.page_index = 0
        self.rename_open = False
        self.mapping_fields = []
        self.fixed_year = ""
        self.fixed_month = ""
        self.selected_source_active = False
        self.source_error = ""
        self.source_success = ""
        self.mapping_revision += 1
        self._clear_editor()

    def _reload(self):
        with rx.session() as session:
            datasets = session.scalars(
                select(UploadedDataset).order_by(
                    UploadedDataset.created_at.desc(), UploadedDataset.id.desc()
                )
            ).all()
            catalogue = [
                UploadedData._dataset_summary(dataset)
                for dataset in datasets
            ]
            self.active_sources = [
                dataset for dataset in catalogue if dataset["active"]
            ]
            selected = next(
                (d for d in datasets if d.id == self.selected_id), None
            )
            if selected is None and datasets:
                selected = datasets[0]
                self.page_index = 0
                self._clear_editor()
            if selected is None:
                self._clear_selection()
            else:
                self.selected_id = selected.id
                self.selected_name = selected.name
                self.original_filename = selected.original_filename
                self.columns = json.loads(selected.column_names_json)
                self.row_count = selected.row_count
                saved_mapping = json.loads(selected.map_mapping_json)
                suggested = self._suggest_mapping(self.columns)
                self.mapping_fields = [
                    {
                        "name": key,
                        "label": label,
                        "value": str(saved_mapping.get(key, suggested[key])),
                    }
                    for key, label in MAPPING_LABELS.items()
                ]
                self.fixed_year = str(saved_mapping.get("fixed_year", ""))
                self.fixed_month = str(saved_mapping.get("fixed_month", ""))
                self.selected_source_active = selected.map_layer_active
                self.mapping_revision += 1
                self.page_index = min(
                    self.page_index,
                    max(0, (selected.row_count - 1) // PAGE_SIZE),
                )
                stored_rows = session.scalars(
                    select(UploadedDatasetRow)
                    .where(UploadedDatasetRow.dataset_id == selected.id)
                    .order_by(
                        UploadedDatasetRow.row_position, UploadedDatasetRow.id
                    )
                    .offset(self.page_index * PAGE_SIZE)
                    .limit(PAGE_SIZE)
                ).all()
                self.rows = [
                    {
                        "id": r.id,
                        "number": self.page_index * PAGE_SIZE + i + 1,
                        "cells": json.loads(r.cell_values_json),
                    }
                    for i, r in enumerate(stored_rows)
                ]
            self.catalogue = catalogue

    @rx.event
    def load_catalogue(self):
        self.loading = True
        self.error = ""
        self._clear_editor()
        self.rename_open = False
        yield
        try:
            self._reload()
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.catalogue = []
            self._clear_selection()
            self.error = "Could not load saved datasets. Please refresh the catalogue to retry."
        finally:
            self.loading = False

    @staticmethod
    def _required_snapshot_dates(year: str, month: str) -> tuple[str, str]:
        clean = UploadedData._fixed_dates(
            {"fixed_year": year, "fixed_month": month}
        )
        if not clean["fixed_year"] or not clean["fixed_month"]:
            raise ValueError(
                "Enter a whole-number year (1–9999) and month (1–12) before importing the CSV. No changes were saved."
            )
        return clean["fixed_year"], clean["fixed_month"]

    @rx.event
    def set_upload_year(self, value: float):
        value = float(value)
        self.upload_year = (
            str(int(value)) if value.is_integer() else str(value)
        )

    @rx.event
    def set_upload_month(self, value: float):
        value = float(value)
        self.upload_month = (
            str(int(value)) if value.is_integer() else str(value)
        )

    @rx.event
    async def import_csv(self, files: list[rx.UploadFile]):
        self.error = ""
        self.success = ""
        try:
            year, month = UploadedData._required_snapshot_dates(
                self.upload_year, self.upload_month
            )
        except ValueError as error:
            self.error = str(error)
            return
        if len(files) != 1:
            self.error = "Select exactly one CSV, then choose Import CSV. Multiple files are not imported."
            return
        self.importing = True
        yield
        try:
            upload = files[0]
            filename = (
                str(upload.name or "").replace("\\", "/").rsplit("/", 1)[-1]
            )
            if "\x00" in filename:
                raise ValueError(
                    "The filename contains an unsupported character. Rename the file and retry."
                )
            data = await upload.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("This CSV exceeds the 20 MB per-file limit.")
            temporary_name = f"csv_{uuid4().hex}.tmp"
            await asyncio.to_thread(self._stage_upload, temporary_name, data)
            yield UploadedData.process_csv(
                temporary_name, filename, year, month
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = (
                str(e)
                if isinstance(e, ValueError)
                else "Could not stage this import. No dataset was saved. Please retry."
            )
            self.importing = False

    @staticmethod
    def _stage_upload(temporary_name: str, data: bytes):
        directory = rx.get_upload_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / temporary_name
        try:
            path.write_bytes(data)
        except Exception as e:
            logging.exception(f"Error: {e}")
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _persist_csv(
        temporary_name: str, filename: str, year: str, month: str
    ) -> tuple[int, int]:
        path = rx.get_upload_dir() / temporary_name
        try:
            year, month = UploadedData._required_snapshot_dates(year, month)
            headers, records = UploadedData._parse_csv(
                filename, path.read_bytes()
            )
            with rx.session() as session:
                with session.begin():
                    dataset = UploadedDataset(
                        name=PurePath(filename).stem,
                        original_filename=filename,
                        column_names_json=json.dumps(
                            headers, ensure_ascii=True
                        ),
                        row_count=len(records),
                        source="uploaded_csv",
                        status="ready",
                        map_mapping_json=json.dumps(
                            {
                                "fixed_year": year,
                                "fixed_month": month,
                            },
                            ensure_ascii=True,
                        ),
                    )
                    session.add(dataset)
                    session.flush()
                    new_id = dataset.id
                    for start in range(0, len(records), 1000):
                        session.execute(
                            insert(UploadedDatasetRow.__table__),
                            [
                                {
                                    "dataset_id": new_id,
                                    "row_position": start + offset,
                                    "cell_values_json": json.dumps(
                                        cells, ensure_ascii=True
                                    ),
                                }
                                for offset, cells in enumerate(
                                    records[start : start + 1000]
                                )
                            ],
                        )
            return new_id, len(records)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError as e:
                logging.exception(f"Error: {e}")

    @rx.event(background=True)
    async def process_csv(
        self, temporary_name: str, filename: str, year: str, month: str
    ):
        try:
            new_id, count = await asyncio.to_thread(
                UploadedData._persist_csv,
                temporary_name,
                filename,
                year,
                month,
            )
            async with self:
                self.selected_id = new_id
                self.page_index = 0
                self.upload_year = ""
                self.upload_month = ""
                self.success = f"Imported {count:,} rows tagged {month}/{year}. Select and apply a map source explicitly; importing alone does not select it."
                self.importing = False
            yield UploadedData.load_catalogue
            yield rx.clear_selected_files("csv_import")
        except Exception as e:
            logging.exception(f"Error: {e}")
            async with self:
                self.error = (
                    str(e)
                    if isinstance(e, ValueError)
                    else "Import failed. No dataset was saved; the transaction was rolled back. Please retry."
                )
                self.importing = False

    @staticmethod
    def _write_source(dataset_id: int, mapping: dict[str, str], remove: bool):
        with rx.session() as session:
            with session.begin():
                if session.get_bind().dialect.name != "sqlite":
                    session.execute(
                        text("SELECT pg_advisory_xact_lock(73120491)")
                    )
                dataset = session.scalar(
                    select(UploadedDataset)
                    .where(UploadedDataset.id == dataset_id)
                    .with_for_update()
                )
                if dataset is None:
                    raise ValueError(
                        "This dataset was deleted. Refresh the catalogue and choose another source."
                    )
                if remove:
                    dataset.map_layer_active = False
                    return
                clean = UploadedData._validate_mapping(
                    json.loads(dataset.column_names_json),
                    dataset.row_count,
                    mapping,
                )
                dataset.map_mapping_json = json.dumps(clean, ensure_ascii=True)
                dataset.map_layer_active = True

    @staticmethod
    def _set_layer_active(dataset_id: int, active: bool):
        with rx.session() as session:
            with session.begin():
                dataset = session.scalar(
                    select(UploadedDataset)
                    .where(UploadedDataset.id == dataset_id)
                    .with_for_update()
                )
                if dataset is None:
                    raise ValueError(
                        "This dataset was deleted. Refresh the catalogue and retry."
                    )
                if active:
                    columns = json.loads(dataset.column_names_json)
                    mapping = json.loads(dataset.map_mapping_json)
                    clean = UploadedData._validate_mapping(
                        columns, dataset.row_count, mapping
                    )
                    dataset.map_mapping_json = json.dumps(
                        clean, ensure_ascii=True
                    )
                dataset.map_layer_active = active

    @rx.event
    def apply_source(self, form_data: dict[str, Any]):
        if self.source_saving or self.importing or self.loading:
            return
        mapping = {key: str(form_data.get(key, "")) for key in MAPPING_LABELS}
        mapping["fixed_year"] = str(
            form_data.get("fixed_year", self.fixed_year)
        )
        mapping["fixed_month"] = str(
            form_data.get("fixed_month", self.fixed_month)
        )
        self.source_error = ""
        self.source_success = ""
        try:
            mapping = UploadedData._validate_mapping(
                self.columns, self.row_count, mapping
            )
        except ValueError as e:
            logging.exception(f"Error: {e}")
            self.source_error = str(e)
            return
        self.source_saving = True
        return UploadedData.persist_source(self.selected_id, mapping, False)

    @rx.event
    def remove_source(self, dataset_id: int):
        if self.source_saving or not dataset_id:
            return
        self.source_error = ""
        self.source_success = ""
        self.source_saving = True
        return UploadedData.persist_source(dataset_id, {}, True)

    @rx.event(background=True)
    async def persist_source(
        self, dataset_id: int, mapping: dict[str, str], remove: bool
    ):
        try:
            await asyncio.to_thread(
                UploadedData._write_source, dataset_id, mapping, remove
            )
            async with self:
                self.source_success = (
                    "Map source removed; its saved mapping is retained for reuse."
                    if remove
                    else "CSV layer applied. It can be displayed with other active layers from the same Year/Month snapshot."
                )
            yield UploadedData.load_catalogue
        except Exception as e:
            logging.exception(f"Error: {e}")
            async with self:
                self.source_error = (
                    str(e)
                    if isinstance(e, ValueError)
                    else "Could not save the map source. No changes were saved; please retry."
                )
        finally:
            async with self:
                self.source_saving = False

    @rx.event
    def suggest_source(self):
        suggested = self._suggest_mapping(self.columns)
        self.mapping_fields = [
            {"name": key, "label": label, "value": suggested[key]}
            for key, label in MAPPING_LABELS.items()
        ]
        self.mapping_revision += 1
        self.source_error = ""
        self.source_success = "Header suggestions restored. Review the mapping and apply to save."

    @rx.event
    def select_dataset(self, dataset_id: int):
        self.selected_id = dataset_id
        self.source_error = ""
        self.source_success = ""
        self.page_index = 0
        self.success = ""
        self.error = ""
        self.rename_open = False
        self._clear_editor()
        try:
            self._reload()
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self._clear_selection()
            self.error = (
                "Could not open this dataset. Refresh the catalogue and retry."
            )

    @rx.event
    def change_page(self, delta: int):
        self.page_index = max(
            0, min(self.page_count - 1, self.page_index + delta)
        )
        self._clear_editor()
        self.error = ""
        try:
            self._reload()
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.rows = []
            self.error = (
                "Could not load this page. Refresh the catalogue and retry."
            )

    @rx.event
    def edit_row(self, row_id: int):
        self.error = ""
        self.success = ""
        row = next((r for r in self.rows if r["id"] == row_id), None)
        if row is None:
            self.error = (
                "This row is no longer in the preview. Refresh and retry."
            )
            return
        self._clear_editor()
        self.editor_mode = "edit"
        self.editor_row_id = row_id
        self.editor_row_number = row["number"]
        self.editor_original = json.dumps(row["cells"], ensure_ascii=True)
        self.editor_fields = [
            {"name": f"cell_{i}", "label": column, "value": row["cells"][i]}
            for i, column in enumerate(self.columns)
        ]

    @rx.event
    def add_row(self):
        self.error = ""
        self.success = ""
        if self.row_count >= MAX_ROWS:
            self._clear_editor()
            self.error = "This dataset has reached the 120,000-row limit. Delete a row before adding another."
            return
        self._clear_editor()
        self.editor_mode = "add"
        self.editor_fields = [
            {"name": f"cell_{i}", "label": column, "value": ""}
            for i, column in enumerate(self.columns)
        ]

    @rx.event
    def cancel_edit(self):
        self._clear_editor()
        self.error = ""

    def _locked_dataset(self, session) -> UploadedDataset:
        dataset = session.scalar(
            select(UploadedDataset)
            .where(UploadedDataset.id == self.selected_id)
            .with_for_update()
        )
        if dataset is None:
            raise ValueError(
                "This dataset was deleted from the shared workspace. Refresh the catalogue."
            )
        return dataset

    def _after_write(self, message: str):
        self._clear_editor()
        self.rename_open = False
        self.success = message
        try:
            self._reload()
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.rows = []
            self.error = "Your change was saved, but the preview could not refresh. Refresh the catalogue; do not repeat the change."

    @rx.event
    def save_row(self, form_data: dict[str, Any]):
        self.error = ""
        self.success = ""
        if self.editor_mode not in ("add", "edit"):
            self.error = "Select a row or choose Add row first."
            return
        cells = [
            str(form_data.get(f"cell_{i}", ""))
            for i in range(len(self.columns))
        ]
        if any(len(cell) > MAX_CELL for cell in cells):
            self.error = "Limit each cell to 32,768 characters. Your changes have not been saved."
            return
        try:
            with rx.session() as session:
                with session.begin():
                    dataset = self._locked_dataset(session)
                    if json.loads(dataset.column_names_json) != self.columns:
                        raise ValueError(
                            "The columns changed. Refresh the catalogue before editing."
                        )
                    if self.editor_mode == "add":
                        if dataset.row_count >= MAX_ROWS:
                            raise ValueError(
                                "This dataset has reached the 120,000-row limit."
                            )
                        last_position = session.scalar(
                            select(
                                func.max(UploadedDatasetRow.row_position)
                            ).where(UploadedDatasetRow.dataset_id == dataset.id)
                        )
                        session.add(
                            UploadedDatasetRow(
                                dataset_id=dataset.id,
                                row_position=0
                                if last_position is None
                                else last_position + 1,
                                cell_values_json=json.dumps(
                                    cells, ensure_ascii=True
                                ),
                            )
                        )
                        dataset.row_count += 1
                        self.page_index = (dataset.row_count - 1) // PAGE_SIZE
                    else:
                        row = session.scalar(
                            select(UploadedDatasetRow)
                            .where(
                                UploadedDatasetRow.id == self.editor_row_id,
                                UploadedDatasetRow.dataset_id == dataset.id,
                            )
                            .with_for_update()
                        )
                        if row is None:
                            raise ValueError(
                                "This row was deleted. Cancel editing and refresh the catalogue."
                            )
                        if json.loads(row.cell_values_json) != json.loads(
                            self.editor_original
                        ):
                            raise ValueError(
                                "Someone changed this row. Cancel editing and refresh before trying again; no changes were saved."
                            )
                        row.cell_values_json = json.dumps(
                            cells, ensure_ascii=True
                        )
            self._after_write("Row saved in the shared workspace.")
        except ValueError as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = "Could not save the row. Your changes have not been saved; please retry."

    @rx.event
    def open_rename(self):
        self.rename_open = not self.rename_open
        self.confirmation = ""
        self.form_revision += 1

    @rx.event
    def rename_dataset(self, form_data: dict[str, Any]):
        name = str(form_data.get("dataset_name", "")).strip()
        self.error = ""
        self.success = ""
        if not name or len(name) > 200 or "\x00" in name:
            self.error = "Use a nonempty dataset name of at most 200 characters, without null characters."
            return
        try:
            with rx.session() as session:
                with session.begin():
                    dataset = self._locked_dataset(session)
                    if dataset.name != self.selected_name:
                        raise ValueError(
                            "Someone renamed this dataset. Refresh the catalogue before renaming."
                        )
                    dataset.name = name
            self._after_write(
                "Dataset renamed. Its original filename is unchanged."
            )
        except ValueError as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = "Could not rename the dataset. No changes were saved."

    @rx.event
    def request_delete(self, target: str):
        if target == "dataset" and self.selected_id:
            self.confirmation = "dataset"
        elif target == "row" and self.editor_mode == "edit":
            self.confirmation = "row"

    @rx.event
    def cancel_delete(self):
        self.confirmation = ""

    @rx.event
    def confirm_delete(self):
        target = self.confirmation
        self.error = ""
        self.success = ""
        if target not in ("dataset", "row"):
            return
        try:
            with rx.session() as session:
                with session.begin():
                    dataset = self._locked_dataset(session)
                    if target == "dataset":
                        session.execute(
                            delete(UploadedDatasetRow).where(
                                UploadedDatasetRow.dataset_id == dataset.id
                            )
                        )
                        session.delete(dataset)
                    else:
                        row = session.scalar(
                            select(UploadedDatasetRow)
                            .where(
                                UploadedDatasetRow.id == self.editor_row_id,
                                UploadedDatasetRow.dataset_id == dataset.id,
                            )
                            .with_for_update()
                        )
                        if row is None:
                            raise ValueError(
                                "This row was already deleted. Cancel editing and refresh."
                            )
                        if json.loads(row.cell_values_json) != json.loads(
                            self.editor_original
                        ):
                            raise ValueError(
                                "Someone changed this row. Cancel editing and refresh before deleting."
                            )
                        session.delete(row)
                        dataset.row_count -= 1
            if target == "dataset":
                self._clear_selection()
            self._after_write(
                "Dataset and all its rows deleted."
                if target == "dataset"
                else "Row deleted from the shared workspace."
            )
        except ValueError as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = str(e)
            self.confirmation = ""
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = "Could not delete the record. No changes were saved."
            self.confirmation = ""
