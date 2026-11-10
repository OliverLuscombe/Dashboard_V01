import unittest

from antarctic_sea_ice_dashboard.states.uploaded_data import (
    MAX_BYTES,
    MAX_COLUMNS,
    MAX_ROWS,
    MAPPING_LABELS,
    UploadedData,
)


class CsvValidationTests(unittest.TestCase):
    def test_preserves_headers_strings_and_quoted_values(self):
        columns, rows = UploadedData._parse_csv(
            "samples.CSV",
            '\ufeff"Lat / degrees",Lon,code,note\r\n-72.5,001,001,"comma, newline\nvalue"\r\n'.encode(
                "utf-8"
            ),
        )
        self.assertEqual(columns, ["Lat / degrees", "Lon", "code", "note"])
        self.assertEqual(
            rows, [["-72.5", "001", "001", "comma, newline\nvalue"]]
        )

    def test_csv_limits_and_header_only_files(self):
        self.assertEqual(MAX_ROWS, 120000)
        self.assertEqual(MAX_BYTES, 20 * 1024 * 1024)
        self.assertEqual(MAX_COLUMNS, 10)
        self.assertEqual(
            UploadedData._parse_csv("empty.csv", b"a,b\n"), (["a", "b"], [])
        )

    def test_accepts_exact_column_and_row_limits(self):
        header = ",".join(f"c{index}" for index in range(MAX_COLUMNS))
        values = ",".join("1" for _ in range(MAX_COLUMNS))
        columns, rows = UploadedData._parse_csv(
            "columns.csv", f"{header}\n{values}\n".encode()
        )
        self.assertEqual(len(columns), MAX_COLUMNS)
        self.assertEqual(rows, [["1"] * MAX_COLUMNS])

        data = f"a\n{'1\n' * MAX_ROWS}".encode()
        columns, rows = UploadedData._parse_csv("rows.csv", data)
        self.assertEqual(columns, ["a"])
        self.assertEqual(len(rows), MAX_ROWS)

    def test_rejects_csv_over_each_size_limit(self):
        with self.assertRaisesRegex(ValueError, "at most 10 columns"):
            UploadedData._parse_csv(
                "too-many-columns.csv",
                f"{','.join(f'c{i}' for i in range(MAX_COLUMNS + 1))}\n".encode(),
            )
        with self.assertRaisesRegex(ValueError, "120,000"):
            UploadedData._parse_csv(
                "too-many-rows.csv",
                f"a\n{'1\n' * (MAX_ROWS + 1)}".encode(),
            )
        with self.assertRaisesRegex(ValueError, "20 MB"):
            UploadedData._parse_csv(
                "too-large.csv", b"a\n" + b"x" * MAX_BYTES
            )

    def test_preserves_leading_zeroes_and_rejects_malformed_rows(self):
        self.assertEqual(
            UploadedData._parse_csv("codes.csv", b"code,value\n001,02\n")[1],
            [["001", "02"]],
        )
        for data in (
            b"a,a\n1,2\n",
            b"a,b\n1\n",
            b"a\n1,2\n",
            b"a\n\n",
            b"a\n\"unclosed",
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                UploadedData._parse_csv("invalid.csv", data)

    def test_requires_whole_number_snapshot_dates(self):
        self.assertEqual(
            UploadedData._required_snapshot_dates("02024", "09"),
            ("2024", "9"),
        )
        for year, month in (
            ("", "9"),
            ("2024", ""),
            ("0", "9"),
            ("10000", "9"),
            ("2024.0", "9"),
            ("2024", "13"),
            ("2024", "September"),
        ):
            with self.subTest(year=year, month=month):
                with self.assertRaises(ValueError):
                    UploadedData._required_snapshot_dates(year, month)

    def test_rejects_invalid_csv_files(self):
        cases = [
            ("wrong.txt", b"a\n1"),
            ("empty.csv", b""),
            ("encoding.csv", b"a\n\xff"),
            ("header.csv", b"a, \n1,2"),
            ("duplicate.csv", b"a,a\n1,2"),
            ("short.csv", b"a,b\n1"),
            ("long.csv", b"a\n1,2"),
            ("quote.csv", b'a\n"unclosed'),
            ("blankline.csv", b"a\n\n"),
            ("too-many-rows.csv", f"a\n{'1\n' * (MAX_ROWS + 1)}".encode()),
        ]
        for filename, data in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    UploadedData._parse_csv(filename, data)


class GeographicMappingTests(unittest.TestCase):
    def test_header_suggestions_only_use_geographic_and_measurement_fields(self):
        columns = [
            "Latitude",
            "Longitude",
            "SEA ICE CONCENTRATION (%)",
            "Sea Surface Temperature (°C)",
            "Wind Speed (m/s)",
            "Air Temperature (°C)",
            "x_coordinate",
            "y_coordinate",
        ]
        mapping = UploadedData._suggest_mapping(columns)
        self.assertEqual(mapping["latitude"], "Latitude")
        self.assertEqual(mapping["longitude"], "Longitude")
        self.assertEqual(
            mapping["sea_ice_concentration"], columns[2]
        )
        self.assertEqual(mapping["sea_surface_temperature"], columns[3])
        self.assertEqual(mapping["wind_speed"], columns[4])
        self.assertEqual(mapping["air_temperature"], columns[5])
        self.assertEqual(set(mapping), set(MAPPING_LABELS))

    def test_mapping_requires_latitude_longitude_and_supported_measurement(self):
        columns = ["Lat", "Lon", "Concentration", "SST"]
        mapping = {
            "latitude": "Lat",
            "longitude": "Lon",
            "sea_ice_concentration": "Concentration",
            "sea_surface_temperature": "SST",
            "fixed_year": "2024",
            "fixed_month": "9",
        }
        clean = UploadedData._validate_mapping(columns, 2, mapping)
        self.assertEqual(clean["fixed_year"], "2024")
        self.assertNotIn("coordinate_mode", clean)
        self.assertNotIn("x_coordinate", clean)

        with self.assertRaisesRegex(ValueError, "Map Latitude"):
            UploadedData._validate_mapping(
                columns, 2, mapping | {"latitude": ""}
            )
        with self.assertRaisesRegex(ValueError, "supported measurement"):
            UploadedData._validate_mapping(
                columns,
                2,
                mapping
                | {
                    "sea_ice_concentration": "",
                    "sea_surface_temperature": "",
                },
            )

    def test_mapping_accepts_only_complete_or_blank_snapshot_dates(self):
        columns = ["Lat", "Lon", "SIC"]
        mapping = {
            "latitude": "Lat",
            "longitude": "Lon",
            "sea_ice_concentration": "SIC",
        }
        clean = UploadedData._validate_mapping(columns, 1, mapping)
        self.assertEqual(clean["fixed_year"], "")
        self.assertEqual(clean["fixed_month"], "")
        for fixed in (
            {"fixed_year": "2024"},
            {"fixed_month": "9"},
            {"fixed_year": "2024.0", "fixed_month": "9"},
            {"fixed_year": "2024", "fixed_month": "13"},
        ):
            with self.subTest(fixed=fixed), self.assertRaises(ValueError):
                UploadedData._validate_mapping(
                    columns, 1, mapping | fixed
                )

    def test_rejects_missing_or_duplicate_mapped_columns(self):
        columns = ["Lat", "Lon", "Value"]
        base = {
            "latitude": "Lat",
            "longitude": "Lon",
            "sea_ice_concentration": "Value",
        }
        with self.assertRaisesRegex(ValueError, "no longer available"):
            UploadedData._validate_mapping(
                columns, 1, base | {"latitude": "Missing"}
            )
        with self.assertRaisesRegex(ValueError, "selected for both"):
            UploadedData._validate_mapping(
                columns, 1, base | {"longitude": "Value"}
            )


if __name__ == "__main__":
    unittest.main()
