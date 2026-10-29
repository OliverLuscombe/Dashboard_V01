import reflex as rx
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


if __name__ == "__main__":
    unittest.main()
