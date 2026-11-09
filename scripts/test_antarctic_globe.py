import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from antarctic_sea_ice_dashboard.states.antarctic_globe import AntarcticGlobe
from antarctic_sea_ice_dashboard.states.snapshot_comparison import (
    SnapshotComparison,
)
from antarctic_sea_ice_dashboard.states.uploaded_data import UploadedData


def dataset(
    dataset_id: int,
    name: str,
    rows: int,
    columns: list[str],
    mapping: dict[str, str],
    active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=dataset_id,
        name=name,
        original_filename=f"{name}.csv",
        row_count=rows,
        column_names_json=json.dumps(columns),
        map_mapping_json=json.dumps(mapping),
        map_layer_active=active,
        created_at=datetime.now(UTC),
    )


def render(datasets, rows_by_dataset, directory, group=""):
    session = MagicMock()
    session.scalars.return_value.all.return_value = datasets
    session.execute.side_effect = [
        [(json.dumps(cells),) for cells in rows]
        for rows in rows_by_dataset
    ]
    with (
        patch(
            "antarctic_sea_ice_dashboard.states.antarctic_globe.rx.session"
        ) as factory,
        patch(
            "antarctic_sea_ice_dashboard.states.antarctic_globe.rx.get_upload_dir",
            return_value=Path(directory),
        ),
    ):
        factory.return_value.__enter__.return_value = session
        result = AntarcticGlobe._render(group, "sea_ice_concentration")
    return result, Path(directory) / result["filename"]


class AntarcticGlobeRenderTests(unittest.TestCase):
    def test_mapping_requires_geographic_columns_and_a_measurement(self):
        columns = ["Latitude", "Longitude", "Concentration"]
        mapping = {
            "latitude": "Latitude",
            "longitude": "Longitude",
            "sea_ice_concentration": "Concentration",
            "fixed_year": "2024",
            "fixed_month": "9",
        }
        clean = UploadedData._validate_mapping(columns, 3, mapping)
        self.assertEqual(clean["latitude"], "Latitude")
        self.assertNotIn("x_coordinate", clean)

        with self.assertRaisesRegex(ValueError, "Map Latitude"):
            UploadedData._validate_mapping(
                columns, 3, mapping | {"latitude": ""}
            )
        with self.assertRaisesRegex(ValueError, "at least one supported"):
            UploadedData._validate_mapping(
                columns,
                3,
                mapping | {"sea_ice_concentration": ""},
            )

    def test_older_geographic_dataset_remains_undated(self):
        source = dataset(
            6,
            "Legacy geographic source",
            1,
            ["Latitude", "Longitude", "SIC"],
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
            },
        )
        summary = UploadedData._dataset_summary(source)
        self.assertTrue(summary["map_ready"])
        self.assertEqual(summary["group_key"], "undated")
        self.assertEqual(summary["snapshot"], "Undated")

    def test_small_years_use_consistent_four_digit_group_keys(self):
        source = dataset(
            7,
            "Old year",
            1,
            ["Latitude", "Longitude", "SIC"],
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
                "fixed_year": "9",
                "fixed_month": "2",
            },
        )
        summary = UploadedData._dataset_summary(source)
        self.assertEqual(summary["group_key"], "0009-02")
        self.assertEqual(summary["snapshot"], "0009-02")

    def test_same_month_active_csv_layers_are_batched_and_invalid_rows_skipped(self):
        columns = ["Latitude", "Longitude", "Concentration"]
        first = dataset(
            1,
            "Fractional",
            3,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "Concentration",
                "fixed_year": "2024",
                "fixed_month": "9",
            },
        )
        second = dataset(
            2,
            "Percent",
            2,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "Concentration",
                "fixed_year": "2024",
                "fixed_month": "9",
            },
        )
        other_month = dataset(
            3,
            "Other month",
            1,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "Concentration",
                "fixed_year": "2024",
                "fixed_month": "10",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            result, point_file = render(
                [other_month, second, first],
                [
                    [["-70", "20", "100"], ["-65", "30", "75"]],
                    [
                        ["-90", "0", "0"],
                        ["-80", "10", "0.5"],
                        ["-91", "20", "0.75"],
                    ],
                ],
                directory,
                "2024-09",
            )
            points = json.loads(point_file.read_text(encoding="utf-8"))["points"]

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["selected_group"], "2024-09")
        self.assertEqual(result["snapshot_label"], "2024-09")
        self.assertEqual(result["total"], 5)
        self.assertEqual(result["valid"], 4)
        self.assertEqual(result["invalid_coordinates"], 1)
        self.assertEqual(result["invalid_readings"], 0)
        self.assertEqual([point[3] for point in points], [100, 75, 0, 50])
        self.assertEqual(
            [point[4] for point in points],
            ["Percent", "Percent", "Fractional", "Fractional"],
        )
        self.assertEqual(
            [layer["name"] for layer in result["layers"]],
            ["Percent", "Fractional"],
        )
        self.assertNotIn("Other month", result["source_name"])

    def test_inactive_csvs_are_grouped_without_rendering_observations(self):
        source = dataset(
            4,
            "Not enabled",
            1,
            ["Latitude", "Longitude", "SIC"],
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
                "fixed_year": "2023",
                "fixed_month": "2",
            },
            active=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            result, point_file = render(
                [source], [[]], directory, "2023-02"
            )
            points = json.loads(point_file.read_text(encoding="utf-8"))["points"]

        self.assertEqual(result["status"], "demo")
        self.assertEqual(result["selected_group"], "2023-02")
        self.assertEqual(result["layers"][0]["active"], False)
        self.assertEqual(points, [])

    def test_nonnumeric_measurements_use_one_shared_color_range(self):
        source = dataset(
            5,
            "Temperature",
            3,
            ["Latitude", "Longitude", "SST"],
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_surface_temperature": "SST",
                "fixed_year": "2024",
                "fixed_month": "9",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            session = MagicMock()
            session.scalars.return_value.all.return_value = [source]
            session.execute.return_value = [
                (json.dumps(row),)
                for row in [
                    ["-90", "0", "-2"],
                    ["-80", "10", "-1"],
                    ["-70", "20", "0"],
                ]
            ]
            with (
                patch(
                    "antarctic_sea_ice_dashboard.states.antarctic_globe.rx.session"
                ) as factory,
                patch(
                    "antarctic_sea_ice_dashboard.states.antarctic_globe.rx.get_upload_dir",
                    return_value=Path(directory),
                ),
            ):
                factory.return_value.__enter__.return_value = session
                result = AntarcticGlobe._render(
                    "2024-09", "sea_surface_temperature"
                )
                points = json.loads(
                    (Path(directory) / result["filename"]).read_text(
                        encoding="utf-8"
                    )
                )["points"]

        self.assertEqual(result["value_range"], "-2–0 °C")
        self.assertEqual([point[2] for point in points], [0, 50, 100])
        self.assertEqual([point[3] for point in points], [-2, -1, 0])
        self.assertEqual(result["average"], "-1 °C")


class SnapshotComparisonTests(unittest.TestCase):
    def test_compares_two_months_in_the_same_year(self):
        columns = ["Latitude", "Longitude", "SIC"]
        september = dataset(
            20,
            "September",
            2,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
                "fixed_year": "2024",
                "fixed_month": "9",
            },
            active=False,
        )
        february = dataset(
            21,
            "February",
            2,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
                "fixed_year": "2024",
                "fixed_month": "2",
            },
            active=False,
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [september, february]
        session.execute.side_effect = [
            [
                (json.dumps(["-70", "0", "80"]),),
                (json.dumps(["-71", "1", "100"]),),
            ],
            [
                (json.dumps(["-70", "0", "20"]),),
                (json.dumps(["-71", "1", "40"]),),
            ],
        ]
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.session"
                ) as factory,
                patch(
                    "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.get_upload_dir",
                    return_value=Path(directory),
                ),
            ):
                factory.return_value.__enter__.return_value = session
                result = SnapshotComparison._compare(
                    "2024-09", "2024-02", "sea_ice_concentration"
                )
            globe_payload = json.loads(
                (Path(directory) / result["globe_filename"]).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(
            [group["key"] for group in result["groups"]],
            ["2024-09", "2024-02"],
        )
        self.assertEqual(result["period_a"], "2024-09")
        self.assertEqual(result["period_b"], "2024-02")
        self.assertEqual(result["mean_a"], "90 %")
        self.assertEqual(result["mean_b"], "30 %")
        self.assertEqual(result["difference"], "-60 %")
        self.assertEqual(result["count_a"], 2)
        self.assertEqual(result["count_b"], 2)
        self.assertIn("2024-02 − 2024-09", result["message"])
        self.assertEqual(result["comparable_cells"], 2)
        self.assertEqual(globe_payload["color_mode"], "difference")
        self.assertEqual(globe_payload["max_abs"], 60)
        self.assertEqual(
            [point[2] for point in globe_payload["points"]], [-60, -60]
        )
        self.assertEqual(globe_payload["cell_size"], "0.5° latitude × 1° longitude")

    def test_difference_globe_averages_within_cells_and_omits_unmatched_cells(self):
        columns = ["Latitude", "Longitude", "SIC"]
        first = dataset(
            40,
            "First",
            3,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
                "fixed_year": "2022",
                "fixed_month": "9",
            },
        )
        second = dataset(
            41,
            "Second",
            3,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_ice_concentration": "SIC",
                "fixed_year": "2023",
                "fixed_month": "9",
            },
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [first, second]
        session.execute.side_effect = [
            [
                (json.dumps(["-70.1", "10.1", "80"]),),
                (json.dumps(["-70.2", "10.2", "100"]),),
                (json.dumps(["-71.1", "11.1", "50"]),),
            ],
            [
                (json.dumps(["-70.3", "10.3", "20"]),),
                (json.dumps(["-70.4", "10.4", "40"]),),
                (json.dumps(["-72.1", "12.1", "90"]),),
            ],
        ]
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.session"
                ) as factory,
                patch(
                    "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.get_upload_dir",
                    return_value=Path(directory),
                ),
            ):
                factory.return_value.__enter__.return_value = session
                result = SnapshotComparison._compare(
                    "2022-09", "2023-09", "sea_ice_concentration"
                )
            points = json.loads(
                (Path(directory) / result["globe_filename"]).read_text(
                    encoding="utf-8"
                )
            )["points"]

        self.assertEqual(result["mean_a"], "76.67 %")
        self.assertEqual(result["mean_b"], "50 %")
        self.assertEqual(result["comparable_cells"], 1)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0][2], -60)
        self.assertEqual(points[0][3:7], [90, 30, 2, 2])
        self.assertEqual(points[0][0:2], [10.5, -70.25])

    def test_comparison_has_no_difference_globe_when_cells_do_not_overlap(self):
        columns = ["Latitude", "Longitude", "SST"]
        first = dataset(
            50,
            "First",
            1,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_surface_temperature": "SST",
                "fixed_year": "2022",
                "fixed_month": "9",
            },
        )
        second = dataset(
            51,
            "Second",
            1,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_surface_temperature": "SST",
                "fixed_year": "2023",
                "fixed_month": "9",
            },
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [first, second]
        session.execute.side_effect = [
            [(json.dumps(["-70", "0", "-2"]),)],
            [(json.dumps(["-70", "2", "0"]),)],
        ]
        with patch(
            "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.session"
        ) as factory:
            factory.return_value.__enter__.return_value = session
            result = SnapshotComparison._compare(
                "2022-09", "2023-09", "sea_surface_temperature"
            )

        self.assertEqual(result["mean_a"], "-2 °C")
        self.assertEqual(result["mean_b"], "0 °C")
        self.assertEqual(result["comparable_cells"], 0)
        self.assertEqual(result["globe_filename"], "")
        self.assertIn("no 0.5° × 1°", result["message"])

    def test_compares_different_years_and_all_csvs_in_each_period(self):
        columns = ["Latitude", "Longitude", "SST"]
        first = dataset(
            30,
            "Year A",
            1,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_surface_temperature": "SST",
                "fixed_year": "2023",
                "fixed_month": "9",
            },
        )
        second = dataset(
            31,
            "Year B",
            2,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_surface_temperature": "SST",
                "fixed_year": "2024",
                "fixed_month": "2",
            },
        )
        extra = dataset(
            32,
            "Another year B file",
            1,
            columns,
            {
                "latitude": "Latitude",
                "longitude": "Longitude",
                "sea_surface_temperature": "SST",
                "fixed_year": "2024",
                "fixed_month": "2",
            },
            active=False,
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [
            first,
            second,
            extra,
        ]
        session.execute.side_effect = [
            [(json.dumps(["-70", "0", "-2"]),)],
            [(json.dumps(["-70", "0", "0"]),)],
            [(json.dumps(["-70", "0", "2"]),)],
        ]
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.session"
                ) as factory,
                patch(
                    "antarctic_sea_ice_dashboard.states.snapshot_comparison.rx.get_upload_dir",
                    return_value=Path(directory),
                ),
            ):
                factory.return_value.__enter__.return_value = session
                result = SnapshotComparison._compare(
                    "2023-09", "2024-02", "sea_surface_temperature"
                )
            globe_payload = json.loads(
                (Path(directory) / result["globe_filename"]).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["mean_a"], "-2 °C")
        self.assertEqual(result["mean_b"], "1 °C")
        self.assertEqual(result["difference"], "+3 °C")
        self.assertEqual(result["count_b"], 2)
        self.assertEqual(result["files_b"], 2)
        self.assertEqual(globe_payload["points"][0][2], 3)


if __name__ == "__main__":
    unittest.main()
