import reflex as rx
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image
from app.models import UploadedDataset
from app.states.overview_grid import OverviewGrid as G, GRID_ROWS


COLUMNS = ["x", "y", "year", "month", "ice", "sst", "cluster", "miz"]
MAPPING = {
    "coordinate_mode": "columns",
    "x_coordinate": "x",
    "y_coordinate": "y",
    "year": "year",
    "month": "month",
    "sea_ice_concentration": "ice",
    "sea_surface_temperature": "sst",
    "cluster": "cluster",
    "marginal_ice_zone": "miz",
}
RECORDS = [
    ["1", "332", "2022", "7", "80", "-2", "pack", "edge"],
    ["1", "332", "2022", "3", "10", "0", "open", "ocean"],
    ["316", "1", "2022", "3", "30", "2", "pack", "edge"],
    ["316", "1", "2022", "3", "99", "99", "ignored", "ignored"],
    ["2", "332", "2022", "3", "NA", "NA", "NA", ""],
    ["2", "332", "2022", "3", "90", "90", "ignored", "ignored"],
    ["3", "332", "2022", "11", "NA", "", "", ""],
    ["1", "332", "2025", "1", "50", "1", "other", "other"],
    ["1", "332", "invalid", "3", "100", "10", "bad", "bad"],
    ["1", "332", "2022", "13", "100", "10", "bad", "bad"],
]


class LockedView(SimpleNamespace):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class OverviewPeriodTests(unittest.TestCase):
    def scan(self, rows=RECORDS, year=0, month=0, mapping=None, columns=None):
        result = G._base_result()
        image, gradient = G._scan(
            ((i, json.dumps(row)) for i, row in enumerate(rows)),
            COLUMNS if columns is None else columns,
            MAPPING if mapping is None else mapping,
            "sea_ice_concentration",
            result,
            year,
            month,
        )
        return result, image, gradient

    def test_initial_period_and_same_period_pixels_cards(self):
        result, image, _ = self.scan()
        self.assertEqual((result["year"], result["month"]), (2022, 3))
        self.assertEqual(
            result["periods"],
            [
                {"year": 2022, "month": 3},
                {"year": 2022, "month": 7},
                {"year": 2022, "month": 11},
                {"year": 2025, "month": 1},
            ],
        )
        self.assertEqual(result["total"], len(RECORDS))
        self.assertEqual(result["invalid_dates"], 2)
        self.assertEqual(result["period_rows"], 5)
        self.assertEqual(result["valid"], 2)
        self.assertEqual(result["duplicates"], 2)
        self.assertEqual(result["invalid_readings"], 1)
        self.assertEqual(result["minimum"], "10")
        self.assertEqual(result["maximum"], "30")
        self.assertEqual(image.getpixel((0, 0))[3], 255)
        self.assertEqual(image.getpixel((315, 331))[3], 255)
        self.assertEqual(image.getpixel((1, 0))[3], 0)
        cards = {m["label"]: m for m in result["metrics"]}
        self.assertEqual(cards["Mean concentration"]["value"], "20.00 %")
        self.assertEqual(
            cards["Pixels with concentration ≥15%"]["value"], "1 pixels"
        )
        self.assertEqual(
            cards["Mean sea-surface temperature"]["value"], "1.00 °C"
        )
        self.assertEqual(
            cards["Distinct CSV cluster labels"]["value"], "2 labels"
        )
        self.assertEqual(
            cards["Distinct MIZ categories"]["value"], "2 categories"
        )
        self.assertIn("n = 2", cards["Mean concentration"]["method"])
        self.assertNotIn("rows", result)
        self.assertNotIn("cells", result)
        self.assertLess(len(json.dumps(result)), 5000)

    def test_monthly_actual_means_samples_and_year_switch(self):
        result, _, _ = self.scan(year=2022, month=7)
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["metrics"][0]["value"], "80.00 %")
        self.assertEqual(
            result["monthly"],
            [
                {"month": 3, "mean": 20.0, "count": 2},
                {"month": 7, "mean": 80.0, "count": 1},
            ],
        )
        self.assertEqual(result["chart_reason"], "")
        other, image, _ = self.scan(year=2025, month=1)
        self.assertEqual(other["metrics"][0]["value"], "50.00 %")
        self.assertEqual(
            other["monthly"], [{"month": 1, "mean": 50.0, "count": 1}]
        )
        self.assertIn("fewer than two", other["chart_reason"])
        self.assertEqual(image.getpixel((315, 331))[3], 0)

    def test_present_period_with_missing_readings_and_nonexistent_period(self):
        result, image, _ = self.scan(year=2022, month=11)
        self.assertEqual(result["period_rows"], 1)
        self.assertEqual(result["valid"], 0)
        self.assertIsNone(image.getbbox())
        self.assertEqual(result["metrics"][0]["value"], "Not available")
        self.assertIn("No valid values", result["metrics"][0]["method"])
        absent, _, _ = self.scan(year=2022, month=12)
        self.assertEqual(absent["period_rows"], 0)
        self.assertEqual(absent["valid"], 0)

    def test_year_only_month_only_and_undated(self):
        for omitted, expected in (("month", (2022, 0)), ("year", (0, 1))):
            mapping = {k: v for k, v in MAPPING.items() if k != omitted}
            result, _, _ = self.scan(mapping=mapping)
            self.assertEqual((result["year"], result["month"]), expected)
            self.assertFalse(result[f"dated_{omitted}"])
        mapping = {
            k: v for k, v in MAPPING.items() if k not in ("year", "month")
        }
        result, _, _ = self.scan(mapping=mapping)
        self.assertEqual(result["periods"], [{"year": 0, "month": 0}])
        self.assertEqual(result["period_rows"], len(RECORDS))
        self.assertIn("month column not mapped", result["chart_reason"])
        view = G()
        self.assertEqual(view.period_label, "Undated snapshot")
        self.assertEqual(view.months, [])

    def test_month_only_aggregates_supported_period_without_invented_year(self):
        mapping = {k: v for k, v in MAPPING.items() if k != "year"}
        result, _, _ = self.scan(mapping=mapping)
        self.assertEqual(result["year"], 0)
        self.assertEqual([m["month"] for m in result["monthly"]], [1, 3, 7])
        self.assertEqual(result["chart_reason"], "")

    def test_missing_columns_and_expected_invalid_readings_do_not_log(self):
        mapping = {
            k: v
            for k, v in MAPPING.items()
            if k
            not in (
                "sea_ice_concentration",
                "sea_surface_temperature",
                "cluster",
                "marginal_ice_zone",
            )
        }
        result, _, _ = self.scan(mapping=mapping)
        self.assertTrue(
            all(card["value"] == "Not available" for card in result["metrics"])
        )
        self.assertTrue(
            all(
                card["method"] == "Column not mapped"
                for card in result["metrics"]
            )
        )
        self.assertIn("concentration column not mapped", result["chart_reason"])
        with patch("app.states.overview_grid.logging.exception") as log:
            for value in ("", "NA", "pack", "NaN", "inf", "1e999"):
                self.assertIsNone(G._number(value))
            log.assert_not_called()

    def test_concentration_range_and_zero_are_defensible(self):
        records = [
            [str(i + 1), "332", "2022", "3", ice, "0", "", ""]
            for i, ice in enumerate(("0", "100", "101", "-1", "inf"))
        ]
        result, _, _ = self.scan(rows=records)
        self.assertEqual(result["metrics"][0]["value"], "50.00 %")
        self.assertIn("n = 2", result["metrics"][0]["method"])
        self.assertEqual(result["metrics"][1]["value"], "1 pixels")

    def test_invalid_mapped_dates_and_decimal_integer_dates(self):
        indices = G._indices(COLUMNS, MAPPING)
        for year, month in (
            ("", "1"),
            ("0", "1"),
            ("10000", "1"),
            ("2022", "0"),
            ("2022", "1.5"),
            ("2022", "January"),
        ):
            self.assertIsNone(
                G._period(["1", "1", year, month, "10", "", "", ""], indices)
            )
        self.assertEqual(
            G._period(["1", "1", "2022.0", "3.0", "10", "", "", ""], indices),
            (2022, 3),
        )
        result, _, _ = self.scan(rows=[RECORDS[-1], RECORDS[-2]])
        self.assertEqual(result["periods"], [])
        self.assertEqual(result["invalid_dates"], 2)
        self.assertEqual(result["valid"], 0)

    def test_full_104912_grid_corners_and_compact_summary(self):
        rows = (["2024", "6", "20"] for _ in range(GRID_ROWS))
        result = G._base_result()
        image, _ = G._scan(
            ((i, json.dumps(row)) for i, row in enumerate(rows)),
            ["year", "month", "ice"],
            {
                "coordinate_mode": "row_order",
                "year": "year",
                "month": "month",
                "sea_ice_concentration": "ice",
            },
            "sea_ice_concentration",
            result,
        )
        self.assertEqual(result["valid"], GRID_ROWS)
        self.assertEqual(result["metrics"][0]["value"], "20.00 %")
        self.assertEqual(result["metrics"][1]["value"], "104,912 pixels")
        for pixel in ((0, 0), (315, 0), (0, 331), (315, 331)):
            self.assertEqual(image.getpixel(pixel)[3], 255)
        self.assertLess(len(json.dumps(result)), 4000)

    def database(self, records=RECORDS):
        dataset = UploadedDataset(
            id=7,
            name="Saved observations",
            row_count=len(records),
            overview_active=True,
            column_names_json=json.dumps(COLUMNS),
            overview_mapping_json=json.dumps(MAPPING),
        )
        session = MagicMock()
        session.scalar.return_value = dataset
        session.execute.return_value = [
            (i, json.dumps(row)) for i, row in enumerate(records)
        ]
        return session

    def test_saved_render_switch_and_inspector_same_period(self):
        session = self.database()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("app.states.overview_grid.rx.session") as factory,
            patch(
                "app.states.overview_grid.rx.get_upload_dir",
                return_value=Path(directory),
            ),
        ):
            factory.return_value.__enter__.return_value = session
            for month, mean in ((3, "20.00 %"), (7, "80.00 %")):
                result = G._render("", 2022, month, 7)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["month"], month)
                self.assertEqual(result["metrics"][0]["value"], mean)
                with Image.open(Path(directory) / result["filename"]) as image:
                    self.assertEqual(image.getpixel((0, 0))[3], 255)
                heading, details = G._lookup(
                    7, "sea_ice_concentration", 1, 332, 2022, month
                )
                self.assertIn("Saved observation", heading)
                self.assertEqual(
                    details[0]["value"], "10" if month == 3 else "80"
                )
            heading, details = G._lookup(
                7, "sea_ice_concentration", 316, 1, 2022, 7
            )
            self.assertIn("No observation", heading)
            self.assertEqual(details, [])
            self.assertEqual(G._render("", 2022, 11, 7)["status"], "empty")
            self.assertIn(
                "selected period", G._render("", 2022, 12, 7)["message"]
            )
            session.execute.assert_called()

    def test_no_rows_and_invalid_date_saved_states(self):
        for records, phrase in (
            ([], "No saved rows"),
            ([RECORDS[-1]], "No valid mapped dates"),
        ):
            with patch("app.states.overview_grid.rx.session") as factory:
                factory.return_value.__enter__.return_value = self.database(
                    records
                )
                result = G._render("")
                self.assertEqual(result["status"], "empty")
                self.assertIn(phrase, result["message"])

    def test_period_controls_support_only_available_values(self):
        state = G()
        state.status = "ready"
        state.dated_year = True
        state.dated_month = True
        state.periods = [
            {"year": 2022, "month": 3},
            {"year": 2022, "month": 7},
            {"year": 2025, "month": 1},
        ]
        state.selected_year, state.selected_month = 2022, 3
        self.assertEqual(state.years, ["2022", "2025"])
        self.assertEqual(state.months, ["3", "7"])
        G.step_month.fn(state, 1)
        self.assertEqual(state.selected_month, 7)
        G.choose_year.fn(state, "2025")
        self.assertEqual((state.selected_year, state.selected_month), (2025, 1))
        G.choose_month.fn(state, "9")
        self.assertEqual(state.selected_month, 1)
        self.assertGreater(state.request_id, 0)
        self.assertGreater(state.inspect_id, 0)


class OverviewStalePeriodTests(unittest.IsolatedAsyncioTestCase):
    async def test_obsolete_inspection_cannot_overwrite_new_period(self):
        state = LockedView(
            inspect_id=5,
            request_id=10,
            selected_year=2022,
            selected_month=7,
            inspection="New period",
            inspection_details=[],
            inspecting=False,
        )
        with (
            patch("app.states.overview_grid.G", create=True),
            patch.object(
                G,
                "_lookup",
                return_value=("Old period", [{"label": "ice", "value": "10"}]),
            ),
        ):
            await G.lookup.fn(
                state, 5, 10, 7, "sea_ice_concentration", 1, 332, 2022, 3
            )
            self.assertEqual(state.inspection, "New period")
            self.assertEqual(state.inspection_details, [])
            await G.lookup.fn(
                state, 4, 9, 7, "sea_ice_concentration", 1, 332, 2022, 7
            )
            self.assertEqual(state.inspection, "New period")

    async def test_obsolete_render_cleans_files_without_changing_state(self):
        state = LockedView(request_id=11)
        result = G._base_result()
        result["filename"], result["legend_filename"] = (
            "old.png",
            "old_legend.png",
        )
        with (
            patch.object(G, "_render", return_value=result),
            patch.object(G, "_remove_files") as cleanup,
        ):
            await G.render.fn(state, 10, "sea_ice_concentration", 2022, 3, 7)
            cleanup.assert_called_once_with(["old.png", "old_legend.png"])
            self.assertFalse(hasattr(state, "monthly"))


if __name__ == "__main__":
    unittest.main()
