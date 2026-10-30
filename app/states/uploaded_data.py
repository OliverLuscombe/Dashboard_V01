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

from sqlalchemy import delete, func, insert, select, text, update
from app.models import UploadedDataset, UploadedDatasetRow


MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 120000
MAX_COLUMNS = 10
MAX_CELL = 32768
PAGE_SIZE = 25
GRID_ROWS = 332 * 316
MAPPING_LABELS: dict[str, str] = {
    "x_coordinate": "x_coordinate · pixel x (required unless row-order)",
    "y_coordinate": "y_coordinate · pixel y (required unless row-order)",
    "latitude": "Latitude · optional metadata",
    "longitude": "Longitude · optional metadata",
    "sea_ice_concentration": "Sea ice concentration (%)",
    "sea_surface_temperature": "Sea-surface temperature (°C)",
    "wind_speed": "Wind speed (m/s)",
    "air_temperature": "Air temperature (°C)",
    "year": "Year",
    "month": "Month",
    "marginal_ice_zone": "Marginal ice zone · optional",
    "cluster": "Cluster · optional",
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
    active_source_id: int = 0
    active_source_name: str = ""
    active_mapping: list[MappingField] = []
    mapping_fields: list[MappingField] = []
    coordinate_mode: str = "columns"
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
            "x_coordinate": ["xcoordinate", "x", "pixelx"],
            "y_coordinate": ["ycoordinate", "y", "pixely"],
            "latitude": ["latitude", "lat", "latitudedegrees"],
            "longitude": ["longitude", "lon", "long", "longitudedegrees"],
            "sea_ice_concentration": [
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
            "year": ["year"],
            "month": ["month"],
            "marginal_ice_zone": ["marginalicezone", "miz"],
            "cluster": [
                "cluster",
                "clusters",
                "clusterid",
                "mlcluster",
                "kmeanscluster",
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
    def _pixel_coordinates(row_position: int) -> tuple[int, int]:
        if not 0 <= row_position < GRID_ROWS:
            raise ValueError(
                "Row position must be within the 332 × 316 pixel grid."
            )
        return row_position % 316 + 1, 332 - row_position // 316

    @staticmethod
    def _validate_mapping(
        columns: list[str], row_count: int, mapping: dict[str, str]
    ) -> dict[str, str]:
        mode = mapping.get("coordinate_mode", "columns")
        if mode not in ("columns", "row_order"):
            raise ValueError("Choose a supported pixel-coordinate mode.")
        clean = {field: mapping.get(field, "") for field in MAPPING_LABELS}
        if any(value and value not in columns for value in clean.values()):
            raise ValueError(
                "A mapped column is no longer available. Refresh the catalogue and retry."
            )
        if mode == "row_order":
            if row_count != GRID_ROWS:
                raise ValueError(
                    "Row-order coordinates require exactly 104,912 rows (332 × 316). Otherwise map both x_coordinate and y_coordinate."
                )
            clean["x_coordinate"] = ""
            clean["y_coordinate"] = ""
        elif not clean["x_coordinate"] or not clean["y_coordinate"]:
            raise ValueError(
                "Map both x_coordinate and y_coordinate columns, or choose row-order generation for a complete 104,912-row grid. Latitude/longitude do not substitute for pixel coordinates."
            )
        elif clean["x_coordinate"] == clean["y_coordinate"]:
            raise ValueError(
                "Choose different source columns for x_coordinate and y_coordinate."
            )
        provided = [value for value in clean.values() if value]
        if len(provided) != len(set(provided)):
            raise ValueError(
                "Map each source column to only one field; use Not provided for absent measurements."
            )
        clean["coordinate_mode"] = mode
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
        self.coordinate_mode = "columns"
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
            catalogue: list[DatasetSummary] = [
                {
                    "id": d.id,
                    "name": d.name,
                    "filename": d.original_filename,
                    "rows": d.row_count,
                    "columns": len(json.loads(d.column_names_json)),
                    "created": d.created_at.strftime("%d %b %Y · %H:%M UTC"),
                }
                for d in datasets
            ]
            active = next((d for d in datasets if d.overview_active), None)
            self.active_source_id = active.id if active else 0
            self.active_source_name = active.name if active else ""
            active_map = (
                json.loads(active.overview_mapping_json) if active else {}
            )
            self.active_mapping = (
                [
                    {
                        "name": key,
                        "label": label,
                        "value": str(active_map.get(key, "")) or "Not provided",
                    }
                    for key, label in MAPPING_LABELS.items()
                ]
                if active
                else []
            )
            if active and active_map.get("coordinate_mode") == "row_order":
                self.active_mapping[0]["value"] = (
                    "Generated: row_position % 316 + 1"
                )
                self.active_mapping[1]["value"] = (
                    "Generated: 332 − row_position // 316"
                )
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
                saved_mapping = json.loads(selected.overview_mapping_json)
                suggested = self._suggest_mapping(self.columns)
                self.mapping_fields = [
                    {
                        "name": key,
                        "label": label,
                        "value": str(saved_mapping.get(key, suggested[key])),
                    }
                    for key, label in MAPPING_LABELS.items()
                ]
                self.coordinate_mode = str(
                    saved_mapping.get("coordinate_mode", "columns")
                )
                self.selected_source_active = selected.overview_active
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

    @rx.event
    async def import_csv(self, files: list[rx.UploadFile]):
        self.error = ""
        self.success = ""
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
            yield UploadedData.process_csv(temporary_name, filename)
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
    def _persist_csv(temporary_name: str, filename: str) -> tuple[int, int]:
        path = rx.get_upload_dir() / temporary_name
        try:
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
    async def process_csv(self, temporary_name: str, filename: str):
        try:
            new_id, count = await asyncio.to_thread(
                UploadedData._persist_csv, temporary_name, filename
            )
            async with self:
                self.selected_id = new_id
                self.page_index = 0
                self.success = f"Imported {count:,} rows. Select and apply an Overview source explicitly; importing alone does not select it."
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
                session.execute(text("SELECT pg_advisory_xact_lock(73120491)"))
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
                    dataset.overview_active = False
                    return
                clean = UploadedData._validate_mapping(
                    json.loads(dataset.column_names_json),
                    dataset.row_count,
                    mapping,
                )
                if clean["coordinate_mode"] == "row_order":
                    count, first, last = session.execute(
                        select(
                            func.count(UploadedDatasetRow.id),
                            func.min(UploadedDatasetRow.row_position),
                            func.max(UploadedDatasetRow.row_position),
                        ).where(UploadedDatasetRow.dataset_id == dataset_id)
                    ).one()
                    if (
                        count != GRID_ROWS
                        or first != 0
                        or last != GRID_ROWS - 1
                    ):
                        raise ValueError(
                            "Row-order generation requires intact row positions 0–104,911. Edited grids with gaps need explicit x/y columns or a fresh complete-grid import."
                        )
                session.execute(
                    update(UploadedDataset)
                    .where(UploadedDataset.overview_active.is_(True))
                    .values(overview_active=False)
                )
                dataset.overview_mapping_json = json.dumps(
                    clean, ensure_ascii=True
                )
                dataset.overview_active = True

    @rx.event
    def apply_source(self, form_data: dict[str, Any]):
        if self.source_saving or self.importing or self.loading:
            return
        mapping = {key: str(form_data.get(key, "")) for key in MAPPING_LABELS}
        mapping["coordinate_mode"] = str(
            form_data.get("coordinate_mode", "columns")
        )
        self.source_error = ""
        self.source_success = ""
        self.source_saving = True
        return UploadedData.persist_source(self.selected_id, mapping, False)

    @rx.event
    def remove_source(self):
        if self.source_saving or not self.active_source_id:
            return
        self.source_error = ""
        self.source_success = ""
        self.source_saving = True
        return UploadedData.persist_source(self.active_source_id, {}, True)

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
                    "Overview source removed; its saved mapping is retained for reuse."
                    if remove
                    else "Overview source and mapping saved. Return to Overview to view the mapped CSV pixel grid. Mapped dates filter pixels, computed summaries and inspection; monthly concentration analysis uses actual available months. Other demo pages remain synthetic."
                )
            yield UploadedData.load_catalogue
        except Exception as e:
            logging.exception(f"Error: {e}")
            async with self:
                self.source_error = (
                    str(e)
                    if isinstance(e, ValueError)
                    else "Could not save the Overview source. No changes were saved; please retry."
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
        self.coordinate_mode = "columns"
        self.mapping_revision += 1
        self.source_error = ""
        self.source_success = "Header suggestions restored. Review them, then apply to save; nothing has changed yet."

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
                        if (
                            dataset.overview_active
                            and json.loads(dataset.overview_mapping_json).get(
                                "coordinate_mode"
                            )
                            == "row_order"
                        ):
                            raise ValueError(
                                "Remove the active row-order Overview source before adding rows; its grid must stay exactly 104,912 rows."
                            )
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
                        if (
                            dataset.overview_active
                            and json.loads(dataset.overview_mapping_json).get(
                                "coordinate_mode"
                            )
                            == "row_order"
                        ):
                            raise ValueError(
                                "Remove the active row-order Overview source before deleting rows; its intact grid positions are required."
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
