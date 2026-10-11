import reflex as rx
import csv
import io
import json
import logging
from pathlib import PurePath
from typing import Any, TypedDict

from sqlalchemy import delete, func, select
from app.models import UploadedDataset, UploadedDatasetRow


MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000
MAX_COLUMNS = 100
MAX_CELL = 32768
PAGE_SIZE = 25


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
    def _parse_csv(
        filename: str, data: bytes
    ) -> tuple[list[str], list[list[str]]]:
        if PurePath(filename).suffix.lower() != ".csv":
            raise ValueError("Choose a file with a .csv extension.")
        if len(data) > MAX_BYTES:
            raise ValueError("This CSV exceeds the 5 MB limit.")
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
                raise ValueError("Use at most 100 columns per CSV.")
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
                    raise ValueError("Use at most 10,000 data rows per CSV.")
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
        committed = False
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
            headers, records = self._parse_csv(filename, data)
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
                    session.add_all(
                        [
                            UploadedDatasetRow(
                                dataset_id=new_id,
                                row_position=i,
                                cell_values_json=json.dumps(
                                    cells, ensure_ascii=True
                                ),
                            )
                            for i, cells in enumerate(records)
                        ]
                    )
            committed = True
            self.selected_id = new_id
            self.page_index = 0
            self.rename_open = False
            self._clear_editor()
            self._reload()
            self.success = f"Imported {len(records):,} rows. Saved in the shared workspace; scientific demos are unchanged."
            yield rx.clear_selected_files("csv_import")
        except ValueError as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = (
                str(e)
                if not committed
                else "The import was saved, but the preview could not refresh. Refresh the catalogue; do not import again."
            )
        except Exception as e:
            logging.exception(f"Error: {type(e).__name__}")
            self.error = (
                "The import was saved, but the preview could not refresh. Refresh the catalogue; do not import again."
                if committed
                else "Import failed. No dataset was saved. Please retry."
            )
        finally:
            self.importing = False

    @rx.event
    def select_dataset(self, dataset_id: int):
        self.selected_id = dataset_id
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
                                "This dataset has reached the 10,000-row limit."
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
