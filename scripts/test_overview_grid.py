import reflex as rx
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from app.models import UploadedDataset
from app.states.overview_grid import OverviewGrid, GRID_ROWS


class OverviewRasterTests(unittest.TestCase):
    def raster(
        self, records, layer="sea_ice_concentration", columns=None, mapping=None
    ):
        columns = columns or ["x", "y", "reading"]
        mapping = mapping or {
            "coordinate_mode": "columns",
            "x_coordinate": "x",
            "y_coordinate": "y",
            layer: "reading",
        }
        result = OverviewGrid._base_result()
        image, gradient = OverviewGrid._raster(
            ((i, json.dumps(row)) for i, row in enumerate(records)),
            columns,
            mapping,
            layer,
            result,
        )
        return result, image, gradient

    def test_r_coordinate_corners_and_transparency(self):
        result, image, gradient = self.raster(
            [
                ["1", "332", "0"],
                ["316", "332", "20"],
                ["1", "1", "50"],
                ["316", "1", "100"],
            ]
        )
        self.assertEqual(image.size, (316, 332))
        self.assertEqual(gradient.size, (256, 1))
        self.assertEqual(image.getpixel((0, 0)), (225, 245, 250, 255))
        self.assertEqual(image.getpixel((315, 331)), (15, 76, 112, 255))
        self.assertEqual(image.getpixel((0, 331))[3], 255)
        self.assertEqual(image.getpixel((315, 0))[3], 255)
        self.assertEqual(image.getpixel((1, 0))[3], 0)
        self.assertEqual(result["valid"], 4)

    def test_finite_numbers_and_coordinate_bounds(self):
        for value in ("", "NA", "NaN", "inf", "-Infinity", "1e999", None, True):
            with self.subTest(value=value):
                self.assertIsNone(OverviewGrid._number(value))
        self.assertEqual(OverviewGrid._number(" 0 "), 0)
        records = [
            ["0", "1", "5"],
            ["317", "1", "5"],
            ["1", "333", "5"],
            ["1.5", "3", "5"],
            ["nan", "1", "5"],
            ["1", "1", "NaN"],
            ["2", "1", ""],
            ["3.0", "1e0", "0"],
        ]
        result, image, _ = self.raster(records)
        self.assertEqual(result["invalid_coordinates"], 5)
        self.assertEqual(result["invalid_readings"], 2)
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["total"], 8)
        self.assertEqual(image.getpixel((2, 331))[3], 255)

    def test_duplicate_first_row_wins_even_if_empty(self):
        result, image, _ = self.raster(
            [
                ["1", "332", ""],
                ["1", "332", "90"],
                ["2", "332", "40"],
                ["2", "332", "80"],
            ]
        )
        self.assertEqual(result["duplicates"], 2)
        self.assertEqual(result["invalid_readings"], 1)
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["minimum"], "40")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(
            result["total"],
            result["valid"]
            + result["duplicates"]
            + result["invalid_coordinates"]
            + result["invalid_readings"],
        )

    def test_full_row_order_grid(self):
        records = ([str(i)] for i in range(GRID_ROWS))
        result, image, _ = self.raster(
            records,
            columns=["reading"],
            mapping={
                "coordinate_mode": "row_order",
                "sea_ice_concentration": "reading",
            },
        )
        self.assertEqual(result["valid"], GRID_ROWS)
        self.assertEqual(result["total"], GRID_ROWS)
        self.assertEqual(image.getpixel((0, 0)), (225, 245, 250, 255))
        self.assertEqual(image.getpixel((315, 331)), (15, 76, 112, 255))
        self.assertLess(
            sum(image.getpixel((315, 0))[:3]), sum(image.getpixel((0, 0))[:3])
        )
        self.assertLess(
            sum(image.getpixel((0, 1))[:3]), sum(image.getpixel((0, 0))[:3])
        )

    def test_empty_and_malformed_cells(self):
        result = OverviewGrid._base_result()
        image, _ = OverviewGrid._raster(
            [(0, "not JSON"), (1, "[]"), (2, json.dumps([1, "1", "5"]))],
            ["x", "y", "value"],
            {
                "coordinate_mode": "columns",
                "x_coordinate": "x",
                "y_coordinate": "y",
                "wind_speed": "value",
            },
            "wind_speed",
            result,
        )
        self.assertEqual(result["invalid_coordinates"], 3)
        self.assertIsNone(image.getbbox())
        self.assertEqual(result["valid"], 0)

    def test_constant_zero_and_extreme_ranges(self):
        result, image, _ = self.raster([["1", "332", "0"], ["2", "332", "0"]])
        self.assertEqual(result["minimum"], result["maximum"])
        self.assertEqual(
            image.getpixel((0, 0)), (*OverviewGrid._continuous_color(0.5), 255)
        )
        for low, high in (("-1e308", "1e308"), ("1e-308", "2e-308")):
            with self.subTest(low=low):
                result, image, _ = self.raster(
                    [["1", "332", low], ["2", "332", high]]
                )
                self.assertEqual(result["valid"], 2)
                self.assertEqual(image.getpixel((0, 0)), (225, 245, 250, 255))
                self.assertEqual(image.getpixel((1, 0)), (15, 76, 112, 255))

    def test_categorical_legend_is_actual_values(self):
        result, image, _ = self.raster(
            [
                ["1", "332", "pack"],
                ["2", "332", "open"],
                ["3", "332", "NA"],
                ["4", "332", "pack"],
            ],
            layer="marginal_ice_zone",
        )
        self.assertEqual(
            [entry["label"] for entry in result["legends"]], ["pack", "open"]
        )
        self.assertEqual(result["valid"], 3)
        self.assertEqual(result["invalid_readings"], 1)
        self.assertEqual(image.getpixel((0, 0)), image.getpixel((3, 0)))
        self.assertNotEqual(image.getpixel((0, 0)), image.getpixel((1, 0)))
        self.assertTrue(
            result["legends"][0]["swatch"].startswith("data:image/png;base64,")
        )
        with self.assertRaisesRegex(ValueError, "more than 32 categories"):
            self.raster(
                [[str(i + 1), "332", f"label-{i}"] for i in range(33)],
                layer="cluster",
            )

    def test_discrete_missing_and_numeric_labels(self):
        self.assertEqual(OverviewGrid._category("2.0"), "2.0")
        self.assertEqual(OverviewGrid._category(" yes "), "yes")
        for value in ("", "NaN", "-inf", "1e999", "x" * 121):
            self.assertIsNone(OverviewGrid._category(value))

    def test_row_order_positions_validated_exactly(self):
        session = MagicMock()
        session.execute.return_value.one.return_value = (
            GRID_ROWS,
            GRID_ROWS,
            0,
            GRID_ROWS - 1,
        )
        OverviewGrid._check_positions(session, 1)
        for values in (
            (GRID_ROWS - 1, GRID_ROWS - 1, 0, GRID_ROWS - 1),
            (GRID_ROWS, GRID_ROWS - 1, 0, GRID_ROWS - 1),
            (GRID_ROWS, GRID_ROWS, 1, GRID_ROWS),
        ):
            session.execute.return_value.one.return_value = values
            with self.assertRaisesRegex(ValueError, "every position"):
                OverviewGrid._check_positions(session, 1)


class OverviewDatabasePathTests(unittest.TestCase):
    def dataset(self, mapping=None):
        return UploadedDataset(
            id=7,
            name="Real CSV",
            row_count=2,
            overview_active=True,
            column_names_json=json.dumps(["x", "y", "reading", "lat", "lon"]),
            overview_mapping_json=json.dumps(
                mapping
                or {
                    "coordinate_mode": "columns",
                    "x_coordinate": "x",
                    "y_coordinate": "y",
                    "sea_ice_concentration": "reading",
                    "latitude": "lat",
                    "longitude": "lon",
                }
            ),
        )

    def session_patch(self, dataset, records):
        session = MagicMock()
        session.scalar.return_value = dataset
        session.execute.return_value = [
            (i, json.dumps(row)) for i, row in enumerate(records)
        ]
        factory = patch("app.states.overview_grid.rx.session")
        return session, factory

    def test_render_writes_compact_png_and_only_returns_small_metadata(self):
        session, factory = self.session_patch(
            self.dataset(),
            [["1", "332", "20", "-70", "30"], ["316", "1", "90", "-72", "35"]],
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            factory as mocked,
            patch(
                "app.states.overview_grid.rx.get_upload_dir",
                return_value=Path(directory),
            ),
        ):
            mocked.return_value.__enter__.return_value = session
            result = OverviewGrid._render("")
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["source_id"], 7)
            self.assertEqual(result["valid"], 2)
            with Image.open(Path(directory) / result["filename"]) as image:
                self.assertEqual(image.size, (316, 332))
                self.assertEqual(image.mode, "RGBA")
            self.assertLess(
                (Path(directory) / result["filename"]).stat().st_size, 20000
            )
            self.assertNotIn("rows", result)
            self.assertNotIn("cells", result)
            session.connection.assert_called_once_with(
                execution_options={"isolation_level": "REPEATABLE READ"}
            )

    def test_no_source_is_demo_but_unmapped_and_empty_are_not(self):
        session, factory = self.session_patch(None, [])
        with factory as mocked:
            mocked.return_value.__enter__.return_value = session
            self.assertEqual(OverviewGrid._render("")["status"], "demo")
        dataset = self.dataset(
            {
                "coordinate_mode": "columns",
                "x_coordinate": "x",
                "y_coordinate": "y",
            }
        )
        session, factory = self.session_patch(dataset, [])
        with factory as mocked:
            mocked.return_value.__enter__.return_value = session
            result = OverviewGrid._render("")
            self.assertEqual(result["status"], "unmapped")
            self.assertEqual(result["layers"], [])
        session, factory = self.session_patch(
            self.dataset(), [["1", "332", "", "", ""]]
        )
        with factory as mocked:
            mocked.return_value.__enter__.return_value = session
            result = OverviewGrid._render("")
            self.assertEqual(result["status"], "empty")
            self.assertEqual(result["filename"], "")

    def test_lookup_actual_metadata_duplicates_and_no_observation(self):
        records = [
            ["1", "332", "", "-70", "30"],
            ["1", "332", "99", "-71", "31"],
        ]
        session, factory = self.session_patch(self.dataset(), records)
        with factory as mocked:
            mocked.return_value.__enter__.return_value = session
            heading, details = OverviewGrid._lookup(
                7, "sea_ice_concentration", 1, 332
            )
            self.assertIn("x=1, y=332", heading)
            self.assertIn("No valid reading", details[0]["value"])
            self.assertEqual(details[1]["value"], "-70°")
            self.assertEqual(details[2]["value"], "30°")
            heading, details = OverviewGrid._lookup(
                7, "sea_ice_concentration", 2, 332
            )
            self.assertIn("No observation at that pixel", heading)
            self.assertEqual(details, [])

    def test_database_failure_is_not_demo_and_png_failure_cleans_up(self):
        session, factory = self.session_patch(
            self.dataset(), [["1", "332", "10", "", ""]]
        )
        session.scalar.side_effect = RuntimeError("read failed")
        with factory as mocked:
            mocked.return_value.__enter__.return_value = session
            with self.assertRaises(RuntimeError):
                OverviewGrid._render("")
        session.scalar.side_effect = None
        with (
            tempfile.TemporaryDirectory() as directory,
            factory as mocked,
            patch(
                "app.states.overview_grid.rx.get_upload_dir",
                return_value=Path(directory),
            ),
            patch(
                "app.states.overview_grid.Image.Image.save",
                side_effect=OSError("write failed"),
            ),
        ):
            mocked.return_value.__enter__.return_value = session
            with self.assertRaises(OSError):
                OverviewGrid._render("")
            self.assertEqual(list(Path(directory).glob("overview_*.png")), [])


if __name__ == "__main__":
    unittest.main()
