import reflex as rx
import unittest
import tempfile
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_utils import run_event

from app.states.uploaded_data import (
    MAX_BYTES,
    MAX_COLUMNS,
    MAX_ROWS,
    GRID_ROWS,
    MAPPING_LABELS,
    UploadedData,
)


class CsvValidationTests(unittest.TestCase):
    def test_preserves_strings_headers_and_quoted_values(self):
        columns, rows = UploadedData._parse_csv(
            "samples.CSV",
            '\ufeff"odd / <header>",date,code,note\r\n<x>,2024-01-01,001,"comma, newline\nvalue"\r\n'.encode(
                "utf-8"
            ),
        )
        self.assertEqual(columns, ["odd / <header>", "date", "code", "note"])
        self.assertEqual(
            rows, [["<x>", "2024-01-01", "001", "comma, newline\nvalue"]]
        )

    def test_header_only_and_blank_strings(self):
        self.assertEqual(
            UploadedData._parse_csv("empty.csv", b"a,b\n"), (["a", "b"], [])
        )
        self.assertEqual(
            UploadedData._parse_csv("blank.csv", b"a,b\n,\n")[1], [["", ""]]
        )

    def test_limits(self):
        self.assertEqual(MAX_ROWS, 120000)
        self.assertEqual(MAX_BYTES, 20 * 1024 * 1024)
        self.assertEqual(MAX_COLUMNS, 10)

    def test_accepts_full_pixel_grid_with_ten_columns(self):
        header = "x_coordinate,y_coordinate,latitude,longitude,sea_ice_concentration,sea_surface_temperature,wind_speed,air_temperature,year,month\n"
        records = "".join(
            f"{position % 316 + 1},{332 - position // 316},-70,30,85,-1.8,8,-15,2024,9\n"
            for position in range(GRID_ROWS)
        )
        data = f"{header}{records}".encode()
        self.assertLess(len(data), MAX_BYTES)
        columns, rows = UploadedData._parse_csv("full-grid.csv", data)
        self.assertEqual(len(columns), 10)
        self.assertEqual(len(rows), 104912)
        self.assertEqual(rows[0][:2], ["1", "332"])
        self.assertEqual(rows[315][:2], ["316", "332"])
        self.assertEqual(rows[316][:2], ["1", "331"])
        self.assertEqual(rows[-1][:2], ["316", "1"])

    def test_rejects_120001_rows_below_byte_limit(self):
        data = f"a\n{'1\n' * 120001}".encode()
        self.assertLess(len(data), MAX_BYTES)
        with self.assertRaisesRegex(ValueError, "120,000"):
            UploadedData._parse_csv("too-many-rows.csv", data)

    def test_accepts_exact_byte_limit(self):
        remaining = MAX_BYTES - 2
        count, tail = divmod(remaining, 32760)
        data = b"".join(
            [b"a\n", (b"v" * 32759 + b"\n") * count, b"v" * (tail - 1), b"\n"]
        )
        self.assertEqual(len(data), MAX_BYTES)
        columns, rows = UploadedData._parse_csv("byte-limit.csv", data)
        self.assertEqual(columns, ["a"])
        self.assertEqual(len(rows), count + 1)
        with self.assertRaisesRegex(ValueError, "20 MB"):
            UploadedData._parse_csv("over-byte-limit.csv", data + b"v")

    def test_accepts_exact_row_limit(self):
        data = f"a\n{'1\n' * MAX_ROWS}".encode()
        columns, rows = UploadedData._parse_csv("row-limit.csv", data)
        self.assertEqual(columns, ["a"])
        self.assertEqual(len(rows), MAX_ROWS)
        self.assertEqual(rows[-1], ["1"])

    def test_accepts_exact_column_limit(self):
        header = ",".join(f"c{i}" for i in range(MAX_COLUMNS))
        values = ",".join("1" for _ in range(MAX_COLUMNS))
        columns, rows = UploadedData._parse_csv(
            "column-limit.csv", f"{header}\n{values}\n".encode()
        )
        self.assertEqual(len(columns), MAX_COLUMNS)
        self.assertEqual(rows, [["1"] * MAX_COLUMNS])

    def test_rejects_invalid_inputs(self):
        cases = [
            ("wrong.txt", b"a\n1"),
            ("empty.csv", b""),
            ("encoding.csv", b"a\n\xff"),
            ("header.csv", b"a, \n1,2"),
            ("duplicate.csv", b"a,a\n1,2"),
            ("duplicate.csv", b"a, a \n1,2"),
            ("short.csv", b"a,b\n1"),
            ("long.csv", b"a\n1,2"),
            ("quote.csv", b'a\n"unclosed'),
            ("blankline.csv", b"a\n\n"),
            ("large.csv", b"a" * (MAX_BYTES + 1)),
            ("rows.csv", f"a\n{'1\n' * (MAX_ROWS + 1)}".encode()),
            (
                "columns.csv",
                f"{','.join(f'c{i}' for i in range(MAX_COLUMNS + 1))}\n"
                f"{','.join('1' for _ in range(MAX_COLUMNS + 1))}\n".encode(),
            ),
        ]
        for filename, data in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    UploadedData._parse_csv(filename, data)


class OverviewMappingTests(unittest.TestCase):
    def test_header_suggestions_ignore_case_spaces_and_punctuation(self):
        columns = [
            " X Coordinate ",
            "Y-coordinate",
            "SEA ICE CONCENTRATION (%)",
            "Sea Surface Temperature (°C)",
            "Wind Speed (m/s)",
            "Air Temperature (°C)",
            "Year",
            "Month",
            "Lat",
            "Lon",
        ]
        mapping = UploadedData._suggest_mapping(columns)
        self.assertEqual(mapping["x_coordinate"], columns[0])
        self.assertEqual(mapping["y_coordinate"], columns[1])
        self.assertEqual(mapping["sea_ice_concentration"], columns[2])
        self.assertEqual(mapping["sea_surface_temperature"], columns[3])
        self.assertEqual(mapping["wind_speed"], columns[4])
        self.assertEqual(mapping["air_temperature"], columns[5])
        self.assertEqual(mapping["latitude"], "Lat")
        self.assertEqual(mapping["longitude"], "Lon")
        self.assertEqual(mapping["cluster"], "")
        self.assertEqual(
            UploadedData._suggest_mapping(["Marginal Ice Zone", "Cluster ID"])[
                "cluster"
            ],
            "Cluster ID",
        )

    def test_manual_mapping_and_absent_measurements(self):
        mapping = UploadedData._validate_mapping(
            ["arbitrary / A", "other B"],
            3,
            {"x_coordinate": "arbitrary / A", "y_coordinate": "other B"},
        )
        self.assertEqual(mapping["x_coordinate"], "arbitrary / A")
        self.assertEqual(mapping["coordinate_mode"], "columns")
        for key in MAPPING_LABELS:
            self.assertIn(key, mapping)
        self.assertEqual(mapping["latitude"], "")
        self.assertEqual(mapping["sea_ice_concentration"], "")

    def test_coordinate_requirements(self):
        for mapping in (
            {},
            {"x_coordinate": "a"},
            {"latitude": "a", "longitude": "b"},
            {"x_coordinate": "a", "y_coordinate": "a"},
            {"x_coordinate": "a", "y_coordinate": "missing"},
        ):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                UploadedData._validate_mapping(["a", "b"], 2, mapping)
        for count in (GRID_ROWS - 1, GRID_ROWS + 1, MAX_ROWS):
            with self.subTest(count=count), self.assertRaises(ValueError):
                UploadedData._validate_mapping(
                    ["a"], count, {"coordinate_mode": "row_order"}
                )
        clean = UploadedData._validate_mapping(
            ["a"], GRID_ROWS, {"coordinate_mode": "row_order"}
        )
        self.assertEqual(clean["coordinate_mode"], "row_order")
        self.assertEqual(clean["latitude"], "")
        self.assertEqual(clean["x_coordinate"], "")

    def test_saved_validation_rejects_duplicate_measurements_and_coordinates(
        self,
    ):
        for first, second in (
            ("sea_ice_concentration", "sea_surface_temperature"),
            ("x_coordinate", "y_coordinate"),
        ):
            with self.subTest(first=first, second=second):
                mapping = {
                    "x_coordinate": "x",
                    "y_coordinate": "y",
                    first: "actual / selected header",
                    second: "actual / selected header",
                }
                with self.assertRaises(ValueError) as error:
                    UploadedData._validate_mapping(
                        ["x", "y", "actual / selected header"], 3, mapping
                    )
                message = str(error.exception)
                self.assertIn("actual / selected header", message)
                self.assertIn(MAPPING_LABELS[first], message)
                self.assertIn(MAPPING_LABELS[second], message)
                self.assertIn("distinct", message)

    def test_write_source_keeps_authoritative_duplicate_validation(self):
        mapping = {
            "x_coordinate": "x",
            "y_coordinate": "y",
            "sea_ice_concentration": "SIC",
            "sea_surface_temperature": "SIC",
        }
        dataset = SimpleNamespace(
            column_names_json=json.dumps(["x", "y", "SIC"]),
            row_count=3,
            overview_mapping_json="{}",
            overview_active=False,
        )
        session = MagicMock()
        session.scalar.return_value = dataset
        with patch("app.states.uploaded_data.rx.session") as factory:
            factory.return_value.__enter__.return_value = session
            with self.assertRaisesRegex(ValueError, "Map each source column"):
                UploadedData._write_source(1, mapping, False)
        self.assertEqual(session.execute.call_count, 1)
        self.assertEqual(dataset.overview_mapping_json, "{}")
        self.assertFalse(dataset.overview_active)
        self.assertIs(
            session.begin.return_value.__exit__.call_args.args[0], ValueError
        )

    def test_fixed_dates_manual_mixed_and_legacy_canonical_mapping(self):
        columns = ["x", "y", "year", "month"]
        base = {"x_coordinate": "x", "y_coordinate": "y"}
        for dates, expected in (
            ({"fixed_year": " 02004 ", "fixed_month": "011"}, ("2004", "11")),
            ({"fixed_year": "9999", "month": "month"}, ("9999", "")),
            ({"year": "year", "fixed_month": "1"}, ("", "1")),
            ({"fixed_year": "1"}, ("1", "")),
            ({"fixed_month": "12"}, ("", "12")),
            ({}, ("", "")),
        ):
            with self.subTest(dates=dates):
                clean = UploadedData._validate_mapping(
                    columns, 82120, base | dates
                )
                self.assertEqual(
                    (clean["fixed_year"], clean["fixed_month"]), expected
                )
                self.assertEqual(clean["year"], dates.get("year", ""))
                self.assertEqual(clean["month"], dates.get("month", ""))
                self.assertEqual(
                    UploadedData._validate_mapping(columns, 82120, clean), clean
                )
        self.assertEqual(
            UploadedData._suggest_mapping(["Latitude", "Longitude"])["year"], ""
        )
        with self.assertRaisesRegex(ValueError, "exactly 104,912"):
            UploadedData._validate_mapping(
                columns, 82120, {"coordinate_mode": "row_order"}
            )

    def test_invalid_or_conflicting_fixed_dates_rejected_by_authoritative_writer(
        self,
    ):
        columns = ["x", "y", "year", "month"]
        base = {"x_coordinate": "x", "y_coordinate": "y"}
        cases = [
            {"fixed_year": value}
            for value in (
                "0",
                "10000",
                "2004.0",
                "2e3",
                "+2004",
                "-1",
                "NaN",
                "year",
                "9" * 100,
                2004,
            )
        ]
        cases.extend(
            {"fixed_month": value}
            for value in ("0", "13", "1.5", "November", "inf", "-1")
        )
        cases.extend(
            (
                {"year": "year", "fixed_year": "2004"},
                {"month": "month", "fixed_month": "11"},
            )
        )
        for dates in cases:
            with self.subTest(dates=dates):
                dataset = SimpleNamespace(
                    column_names_json=json.dumps(columns),
                    row_count=82120,
                    overview_mapping_json="{}",
                    overview_active=False,
                )
                session = MagicMock()
                session.scalar.return_value = dataset
                with patch("app.states.uploaded_data.rx.session") as factory:
                    factory.return_value.__enter__.return_value = session
                    with self.assertRaisesRegex(
                        ValueError, "No changes were saved"
                    ):
                        UploadedData._write_source(1, base | dates, False)
                self.assertEqual(session.execute.call_count, 1)
                self.assertEqual(dataset.overview_mapping_json, "{}")
                self.assertFalse(dataset.overview_active)

    def test_fixed_mapping_save_reload_and_legacy_defaults_leave_rows_untouched(
        self,
    ):
        dataset = SimpleNamespace(
            id=1,
            name="No filename inference",
            original_filename="200411.csv",
            row_count=82120,
            created_at=datetime.now(UTC),
            overview_active=False,
            column_names_json=json.dumps(["x", "y", "ice"]),
            overview_mapping_json="{}",
        )
        session = MagicMock()
        session.scalar.return_value = dataset
        session.scalars.return_value.all.side_effect = [
            [dataset],
            [],
            [dataset],
            [],
        ]
        mapping = {
            "x_coordinate": "x",
            "y_coordinate": "y",
            "sea_ice_concentration": "ice",
            "fixed_year": " 02004 ",
            "fixed_month": "011",
        }
        with patch("app.states.uploaded_data.rx.session") as factory:
            factory.return_value.__enter__.return_value = session
            UploadedData._write_source(1, mapping, False)
            saved = json.loads(dataset.overview_mapping_json)
            self.assertEqual(saved["fixed_year"], "2004")
            self.assertEqual(saved["fixed_month"], "11")
            self.assertEqual(session.execute.call_count, 2)
            session.add.assert_not_called()
            state = UploadedData()
            state._reload()
            self.assertEqual(
                (state.fixed_year, state.fixed_month), ("2004", "11")
            )
            active = {field["name"]: field for field in state.active_mapping}
            self.assertIn("manual metadata", active["fixed_year"]["label"])
            self.assertEqual(active["fixed_month"]["value"], "11")
            dataset.overview_mapping_json = json.dumps(
                {k: v for k, v in saved.items() if not k.startswith("fixed_")}
            )
            state._reload()
            self.assertEqual((state.fixed_year, state.fixed_month), ("", ""))
            self.assertEqual(dataset.row_count, 82120)
            self.assertEqual(
                dataset.column_names_json, json.dumps(["x", "y", "ice"])
            )
        state.fixed_year, state.fixed_month = "2004", "11"
        UploadedData.suggest_source.fn(state)
        self.assertEqual((state.fixed_year, state.fixed_month), ("", ""))
        state.fixed_year, state.fixed_month = "2004", "11"
        state._clear_selection()
        self.assertEqual((state.fixed_year, state.fixed_month), ("", ""))

    def test_pixel_order_boundaries(self):
        for position, expected in [
            (0, (1, 332)),
            (315, (316, 332)),
            (316, (1, 331)),
            (104911, (316, 1)),
        ]:
            self.assertEqual(
                UploadedData._pixel_coordinates(position), expected
            )
        for position in (-1, GRID_ROWS):
            with self.assertRaises(ValueError):
                UploadedData._pixel_coordinates(position)

    def test_chunked_import_uses_one_transaction_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "staged.tmp"
            path.write_bytes(f"a\n{'1\n' * 2001}".encode())
            session = MagicMock()
            session.flush.side_effect = lambda: setattr(
                session.add.call_args.args[0], "id", 42
            )
            with (
                patch(
                    "app.states.uploaded_data.rx.get_upload_dir",
                    return_value=Path(directory),
                ),
                patch("app.states.uploaded_data.rx.session") as factory,
            ):
                factory.return_value.__enter__.return_value = session
                self.assertEqual(
                    UploadedData._persist_csv("staged.tmp", "test.csv"),
                    (42, 2001),
                )
            self.assertEqual(session.begin.call_count, 1)
            self.assertEqual(
                [len(call.args[1]) for call in session.execute.call_args_list],
                [1000, 1000, 1],
            )
            self.assertFalse(path.exists())

    def test_insert_failure_exits_transaction_with_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "staged.tmp"
            path.write_bytes(f"a\n{'1\n' * 1001}".encode())
            session = MagicMock()
            session.flush.side_effect = lambda: setattr(
                session.add.call_args.args[0], "id", 42
            )
            session.execute.side_effect = [None, RuntimeError("batch failed")]
            with (
                patch(
                    "app.states.uploaded_data.rx.get_upload_dir",
                    return_value=Path(directory),
                ),
                patch("app.states.uploaded_data.rx.session") as factory,
            ):
                factory.return_value.__enter__.return_value = session
                with self.assertRaisesRegex(RuntimeError, "batch failed"):
                    UploadedData._persist_csv("staged.tmp", "test.csv")
            self.assertIs(
                session.begin.return_value.__exit__.call_args.args[0],
                RuntimeError,
            )
            session.commit.assert_not_called()
            self.assertFalse(path.exists())


class OverviewMappingEventTests(unittest.IsolatedAsyncioTestCase):
    def _make_state(self, columns: list[str], row_count: int) -> UploadedData:
        state = UploadedData()
        state.selected_id = 1
        state.columns = columns
        state.row_count = row_count
        state.source_saving = False
        state.source_error = ""
        state.source_success = ""
        return state

    async def test_duplicate_submit_reports_fields_without_scheduling_save(
        self,
    ):
        for first, second in (
            ("sea_ice_concentration", "sea_surface_temperature"),
            ("x_coordinate", "y_coordinate"),
            ("x_coordinate", "sea_ice_concentration"),
        ):
            with self.subTest(first=first, second=second):
                header = "actual / selected header"
                form = {
                    "coordinate_mode": "columns",
                    "x_coordinate": "x",
                    "y_coordinate": "y",
                    first: header,
                    second: header,
                }
                state = self._make_state(["x", "y", header], 3)
                state.source_success = "Old success"
                revision = state.mapping_revision
                with (
                    patch.object(UploadedData, "persist_source") as save,
                    patch.object(UploadedData, "_write_source") as write,
                ):
                    await run_event(state.apply_source, form)
                save.assert_not_called()
                write.assert_not_called()
                self.assertFalse(state.source_saving)
                self.assertEqual(state.source_success, "")
                self.assertEqual(state.mapping_revision, revision)
                self.assertIn(header, state.source_error)
                self.assertIn(MAPPING_LABELS[first], state.source_error)
                self.assertIn(MAPPING_LABELS[second], state.source_error)
                self.assertIn("distinct", state.source_error)
                if first != "x_coordinate" or second != "y_coordinate":
                    self.assertIn("Not provided", state.source_error)
                self.assertEqual(
                    state.source_error,
                    UploadedData._duplicate_mapping_error(form),
                )

    async def test_independent_mapping_schedules_save_without_dropping_measurements(
        self,
    ):
        form = {
            "coordinate_mode": "columns",
            "x_coordinate": "x",
            "y_coordinate": "y",
            "sea_ice_concentration": "SIC",
            "sea_surface_temperature": "SST",
        }
        state = self._make_state(["x", "y", "SIC", "SST"], 3)
        state.source_error = "Old error"
        with patch.object(
            UploadedData, "persist_source", return_value=None
        ) as save:
            await run_event(state.apply_source, form)
        self.assertTrue(state.source_saving)
        self.assertEqual(state.source_error, "")
        expected = {field: form.get(field, "") for field in MAPPING_LABELS}
        expected["coordinate_mode"] = "columns"
        expected["fixed_year"] = ""
        expected["fixed_month"] = ""
        save.assert_called_once_with(1, expected, False)
        self.assertEqual(
            UploadedData._validate_mapping(state.columns, 3, expected), expected
        )

    async def test_fixed_dates_form_rejects_before_background_save(self):
        for dates in (
            {"fixed_year": "10000"},
            {"fixed_year": "2004.0"},
            {"fixed_month": "13"},
            {"fixed_month": "November"},
            {"year": "Year", "fixed_year": "2004"},
            {"month": "Month", "fixed_month": "11"},
        ):
            with self.subTest(dates=dates):
                state = self._make_state(["x", "y", "Year", "Month"], 82120)
                form = {"x_coordinate": "x", "y_coordinate": "y"} | dates
                with patch.object(UploadedData, "persist_source") as save:
                    await run_event(state.apply_source, form)
                save.assert_not_called()
                self.assertFalse(state.source_saving)
                self.assertIn("No changes were saved", state.source_error)
                with self.assertRaises(ValueError) as error:
                    UploadedData._validate_mapping(state.columns, 82120, form)
                self.assertEqual(state.source_error, str(error.exception))

    async def test_fixed_dates_pass_canonically_to_save(self):
        state = self._make_state(["x", "y", "Month"], 82120)
        for dates in (
            {"fixed_year": " 02004 ", "fixed_month": "011"},
            {"fixed_year": "2004", "month": "Month"},
        ):
            state.source_saving = False
            with patch.object(
                UploadedData, "persist_source", return_value=None
            ) as save:
                await run_event(
                    state.apply_source,
                    {"x_coordinate": "x", "y_coordinate": "y"} | dates,
                )
            self.assertTrue(state.source_saving)
            self.assertEqual(state.source_error, "")
            submitted = save.call_args.args[1]
            self.assertEqual(submitted["fixed_year"], "2004")
            self.assertEqual(
                submitted["fixed_month"], "11" if "fixed_month" in dates else ""
            )
            self.assertEqual(submitted["month"], dates.get("month", ""))

    async def test_row_order_ignores_duplicate_coordinate_selections(self):
        form = {
            "coordinate_mode": "row_order",
            "x_coordinate": "SIC",
            "y_coordinate": "SIC",
            "sea_ice_concentration": "SIC",
        }
        state = self._make_state(["SIC"], GRID_ROWS)
        with patch.object(
            UploadedData, "persist_source", return_value=None
        ) as save:
            await run_event(state.apply_source, form)
        self.assertTrue(state.source_saving)
        self.assertEqual(state.source_error, "")
        save.assert_called_once()
        submitted = save.call_args.args[1]
        self.assertEqual(submitted["sea_ice_concentration"], "SIC")
        clean = UploadedData._validate_mapping(["SIC"], GRID_ROWS, submitted)
        self.assertEqual(clean["x_coordinate"], "")
        self.assertEqual(clean["y_coordinate"], "")
        self.assertEqual(clean["sea_ice_concentration"], "SIC")

    async def test_row_order_rejects_duplicate_non_coordinate_fields(self):
        form = {
            "coordinate_mode": "row_order",
            "x_coordinate": "SIC",
            "y_coordinate": "SIC",
            "sea_ice_concentration": "SIC",
            "sea_surface_temperature": "SIC",
        }
        state = self._make_state(["SIC"], GRID_ROWS)
        with (
            patch.object(UploadedData, "persist_source") as save,
            patch.object(UploadedData, "_write_source") as write,
        ):
            await run_event(state.apply_source, form)
        save.assert_not_called()
        write.assert_not_called()
        self.assertFalse(state.source_saving)
        self.assertIn('CSV column "SIC"', state.source_error)
        self.assertIn(
            MAPPING_LABELS["sea_ice_concentration"], state.source_error
        )
        self.assertIn(
            MAPPING_LABELS["sea_surface_temperature"], state.source_error
        )
        self.assertNotIn(MAPPING_LABELS["x_coordinate"], state.source_error)
        self.assertNotIn(MAPPING_LABELS["y_coordinate"], state.source_error)
        self.assertIn("Not provided", state.source_error)
        with self.assertRaises(ValueError) as error:
            UploadedData._validate_mapping(["SIC"], GRID_ROWS, form)
        self.assertEqual(str(error.exception), state.source_error)


if __name__ == "__main__":
    unittest.main()
