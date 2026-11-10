import reflex as rx

import json
import logging
import re
from pathlib import Path
from typing import Literal, TypedDict

from sqlalchemy import insert, select, text

from antarctic_sea_ice_dashboard.models import (
    UploadedDataset,
    UploadedDatasetRow,
)
from antarctic_sea_ice_dashboard.states.uploaded_data import (
    MAX_BYTES,
    UploadedData,
)


BATCH_SIZE = 1000
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class RestoreResult(TypedDict):
    filename: str
    status: Literal["inserted", "skipped"]
    dataset_id: int
    inserted_rows: int
    active: bool


def infer_snapshot(path: Path) -> dict[str, str]:
    match = re.match(r"([0-9]{4})([0-9]{2})(?![0-9])", path.name)
    if match is None:
        raise ValueError(
            "Filename must start with exactly six ASCII digits YYYYMM."
        )
    year, month = UploadedData._required_snapshot_dates(*match.groups())
    return {"fixed_year": year, "fixed_month": month}


def suggested_mapping(
    columns: list[str], row_count: int, dates: dict[str, str]
) -> tuple[dict[str, str], bool]:
    suggested = UploadedData._suggest_mapping(columns) | dates
    try:
        return UploadedData._validate_mapping(
            columns, row_count, suggested
        ), True
    except ValueError:
        return dates.copy(), False


def restore_file(path: Path) -> RestoreResult:
    """Restore one missing filename atomically; never modify an existing dataset."""
    try:
        with rx.session() as session:
            with session.begin():
                # Serialize concurrent restorers before the filename existence check.
                if session.get_bind().dialect.name == "postgresql":
                    session.execute(
                        text("SELECT pg_advisory_xact_lock(73120491)")
                    )
                elif session.get_bind().dialect.name == "sqlite":
                    session.execute(text("BEGIN IMMEDIATE"))
                existing = session.scalar(
                    select(UploadedDataset)
                    .where(UploadedDataset.original_filename == path.name)
                    .order_by(UploadedDataset.id)
                    .limit(1)
                )
                if existing is not None:
                    return {
                        "filename": path.name,
                        "status": "skipped",
                        "dataset_id": existing.id,
                        "inserted_rows": 0,
                        "active": existing.map_layer_active,
                    }
                dates = infer_snapshot(path)
                with path.open("rb") as file:
                    data = file.read(MAX_BYTES + 1)
                columns, records = UploadedData._parse_csv(path.name, data)
                del data
                mapping, active = suggested_mapping(
                    columns, len(records), dates
                )
                dataset = UploadedDataset(
                    name=path.stem,
                    original_filename=path.name,
                    column_names_json=json.dumps(columns, ensure_ascii=True),
                    row_count=len(records),
                    source="uploaded_csv",
                    status="ready",
                    map_mapping_json=json.dumps(mapping, ensure_ascii=True),
                    map_layer_active=active,
                )
                session.add(dataset)
                session.flush()
                dataset_id = dataset.id
                for start in range(0, len(records), BATCH_SIZE):
                    session.execute(
                        insert(UploadedDatasetRow.__table__),
                        [
                            {
                                "dataset_id": dataset_id,
                                "row_position": start + offset,
                                "cell_values_json": json.dumps(
                                    cells, ensure_ascii=True
                                ),
                            }
                            for offset, cells in enumerate(
                                records[start : start + BATCH_SIZE]
                            )
                        ],
                    )
                result: RestoreResult = {
                    "filename": path.name,
                    "status": "inserted",
                    "dataset_id": dataset_id,
                    "inserted_rows": len(records),
                    "active": active,
                }
        return result
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


def main() -> int:
    paths = sorted(DATA_DIR.glob("*.csv"))
    if not paths:
        print("No bundled CSV files found; nothing restored.")
        return 1
    inserted_rows = inserted_files = skipped_files = failed_files = 0
    for path in paths:
        try:
            result = restore_file(path)
        except Exception:
            logging.exception("Unexpected error")
            failed_files += 1
            print(
                f"FAILED {path.name}: no changes committed for this file; see error log."
            )
            continue
        if result["status"] == "skipped":
            skipped_files += 1
            print(
                f"SKIP {path.name}: existing dataset preserved; inserted 0 rows."
            )
        else:
            inserted_files += 1
            inserted_rows += result["inserted_rows"]
            layer = (
                "active supported layer"
                if result["active"]
                else "inactive; date metadata only"
            )
            print(
                f"INSERT {path.name}: {result['inserted_rows']:,} rows; {layer}."
            )
    print(
        f"Finished: {inserted_files} inserted files, {inserted_rows:,} inserted rows, "
        f"{skipped_files} skipped files, {failed_files} failed files."
    )
    return 1 if failed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
