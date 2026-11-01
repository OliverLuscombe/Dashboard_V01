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
        view.dated_year = False
        view.dated_month = False
        view.selected_year = 0
        view.selected_month = 0
        view.periods = []
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
            for value in ("", "NA", "pack", "NaN", "inf", "1e999", 10**400):
                self.assertIsNone(G._number(value))
            log.assert_not_called()

    def test_discrete_raster_classifies_without_numeric_conversion_or_logs(
        self,
    ):
        for layer in ("cluster", "marginal_ice_zone"):
            with self.subTest(layer=layer):
                result = G._base_result()
                with (
                    patch.object(G, "_number") as number,
                    patch("app.states.overview_grid.logging.exception") as log,
                ):
                    image, _ = G._raster(
                        (
                            (i, json.dumps([label]))
                            for i, label in enumerate(
                                ("pack", "edge", "pack", "", "NA", "inf")
                            )
                        ),
                        ["category"],
                        {"coordinate_mode": "row_order", layer: "category"},
                        layer,
                        result,
                    )
                    number.assert_not_called()
                    log.assert_not_called()
                self.assertEqual(result["valid"], 3)
                self.assertEqual(result["invalid_readings"], 3)
                self.assertEqual(
                    [entry["label"] for entry in result["legends"]],
                    ["pack", "edge"],
                )
                self.assertEqual(image.getpixel((0, 0)), image.getpixel((2, 0)))
                self.assertEqual(image.getpixel((0, 0))[3], 255)
                self.assertEqual(image.getpixel((3, 0))[3], 0)

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

    def database(self, records=RECORDS, mapping=None, columns=None):
        dataset = UploadedDataset(
            id=7,
            name="Saved observations",
            row_count=len(records),
            overview_active=True,
            column_names_json=json.dumps(
                COLUMNS if columns is None else columns
            ),
            overview_mapping_json=json.dumps(
                MAPPING if mapping is None else mapping
            ),
        )
        session = MagicMock()
        session.scalar.return_value = dataset
        session.execute.return_value = [
            (i, json.dumps(row)) for i, row in enumerate(records)
        ]
        return session

    def test_manual_only_dates_apply_to_every_row_cards_and_single_observed_month(
        self,
    ):
        columns = ["x", "y", "ice"]
        mapping = {
            "coordinate_mode": "columns",
            "x_coordinate": "x",
            "y_coordinate": "y",
            "sea_ice_concentration": "ice",
            "fixed_year": "2004",
            "fixed_month": "11",
        }
        rows = [["1", "332", "10"], ["316", "1", "30"]]
        result, image, _ = self.scan(
            rows=rows, columns=columns, mapping=mapping
        )
        self.assertEqual(result["periods"], [{"year": 2004, "month": 11}])
        self.assertEqual((result["year"], result["month"]), (2004, 11))
        self.assertTrue(result["dated_year"] and result["dated_month"])
        self.assertEqual(result["period_rows"], 2)
        self.assertEqual(result["invalid_dates"], 0)
        self.assertEqual(result["metrics"][0]["value"], "20.00 %")
        self.assertEqual(
            result["monthly"], [{"month": 11, "mean": 20.0, "count": 2}]
        )
        self.assertIn("fewer than two observed months", result["chart_reason"])
        self.assertIn("Manual metadata", result["year_source"])
        self.assertIn("Manual metadata", result["month_source"])
        self.assertEqual(image.getpixel((315, 331))[3], 255)
        indices = G._indices(columns, mapping)
        self.assertNotIn("fixed_year", indices)
        self.assertNotIn("fixed_month", indices)
        self.assertEqual(G._period(rows[0], indices, mapping), (2004, 11))
        self.assertEqual(G._period(rows[0], indices), (0, 0))
        with self.assertRaisesRegex(
            ValueError, "both a CSV column and a manual value"
        ):
            G._period(rows[0], indices, mapping | {"year": "x"})
        absent, _, _ = self.scan(
            rows=rows, columns=columns, mapping=mapping, year=2004, month=12
        )
        self.assertEqual(absent["period_rows"], 0)
        state = G()
        state.status = "ready"
        state.periods = result["periods"]
        state.dated_year = state.dated_month = True
        state.selected_year, state.selected_month = 2004, 11
        self.assertEqual(state.years, ["2004"])
        self.assertEqual(state.months, ["11"])
        self.assertEqual(state.period_label, "November 2004")
        G.toggle_play.fn(state)
        self.assertFalse(state.playing)
        G.step_month.fn(state, 1)
        G.choose_month.fn(state, "12")
        G.choose_year.fn(state, "2005")
        self.assertEqual(
            (state.selected_year, state.selected_month), (2004, 11)
        )

    def test_mixed_manual_csv_dates_and_partial_metadata(self):
        base = {
            "coordinate_mode": "columns",
            "x_coordinate": "x",
            "y_coordinate": "y",
            "sea_ice_concentration": "ice",
        }
        columns = ["x", "y", "ice", "date"]
        rows = [["1", "332", "10", "3"], ["1", "332", "80", "7"]]
        mapping = base | {"fixed_year": "2004", "month": "date"}
        result, _, _ = self.scan(
            rows=rows, columns=columns, mapping=mapping, year=2004, month=7
        )
        self.assertEqual(
            result["periods"],
            [{"year": 2004, "month": 3}, {"year": 2004, "month": 7}],
        )
        self.assertEqual(result["metrics"][0]["value"], "80.00 %")
        self.assertEqual([m["month"] for m in result["monthly"]], [3, 7])
        self.assertEqual(result["chart_reason"], "")
        self.assertEqual(result["month_source"], "CSV column: date")
        rows = [["1", "332", "10", "2004"], ["1", "332", "80", "2005"]]
        mapping = base | {"year": "date", "fixed_month": "11"}
        result, _, _ = self.scan(
            rows=rows, columns=columns, mapping=mapping, year=2005, month=11
        )
        self.assertEqual(
            result["periods"],
            [{"year": 2004, "month": 11}, {"year": 2005, "month": 11}],
        )
        self.assertEqual(result["metrics"][0]["value"], "80.00 %")
        self.assertEqual(
            result["monthly"], [{"month": 11, "mean": 80.0, "count": 1}]
        )
        self.assertEqual(result["year_source"], "CSV column: date")
        for dates, expected in (
            ({"fixed_year": "2004"}, (2004, 0)),
            ({"fixed_month": "11"}, (0, 11)),
            ({}, (0, 0)),
        ):
            with self.subTest(dates=dates):
                result, _, _ = self.scan(
                    rows=rows, columns=columns, mapping=base | dates
                )
                self.assertEqual((result["year"], result["month"]), expected)
                self.assertEqual(result["invalid_dates"], 0)
                self.assertEqual(result["period_rows"], len(rows))
                self.assertEqual(result["dated_year"], bool(expected[0]))
                self.assertEqual(result["dated_month"], bool(expected[1]))

    def test_manual_saved_render_and_inspector_use_identical_period_logic(self):
        columns = ["x", "y", "ice", "date"]
        base = {
            "coordinate_mode": "columns",
            "x_coordinate": "x",
            "y_coordinate": "y",
            "sea_ice_concentration": "ice",
        }
        cases = (
            (
                {"fixed_year": "2004", "fixed_month": "11"},
                ["unused"],
                [(2004, 11, "10")],
            ),
            (
                {"fixed_year": "2004", "month": "date"},
                ["3", "7"],
                [(2004, 3, "10"), (2004, 7, "80")],
            ),
            (
                {"year": "date", "fixed_month": "11"},
                ["2004", "2005"],
                [(2004, 11, "10"), (2005, 11, "80")],
            ),
            ({"fixed_month": "11"}, ["unused"], [(0, 11, "10")]),
            ({"fixed_year": "2004"}, ["unused"], [(2004, 0, "10")]),
            ({}, ["unused"], [(0, 0, "10")]),
        )
        for dates, values, periods in cases:
            with self.subTest(dates=dates):
                mapping = base | dates
                rows = [
                    ["1", "332", ice, value]
                    for ice, value in zip(("10", "80"), values)
                ]
                session = self.database(rows, mapping=mapping, columns=columns)
                with (
                    tempfile.TemporaryDirectory() as directory,
                    patch("app.states.overview_grid.rx.session") as factory,
                    patch(
                        "app.states.overview_grid.rx.get_upload_dir",
                        return_value=Path(directory),
                    ),
                ):
                    factory.return_value.__enter__.return_value = session
                    for year, month, reading in periods:
                        result = G._render("", year, month, 7)
                        self.assertEqual(result["status"], "ready")
                        self.assertEqual(
                            (result["year"], result["month"]), (year, month)
                        )
                        self.assertEqual(
                            result["metrics"][0]["value"],
                            f"{float(reading):.2f} %",
                        )
                        heading, details = G._lookup(
                            7, "sea_ice_concentration", 1, 332, year, month
                        )
                        self.assertIn("Saved observation", heading)
                        self.assertEqual(details[0]["value"], reading)
                        for key in ("year", "month"):
                            date_details = [
                                detail
                                for detail in details
                                if detail["label"].startswith(
                                    f"{key.title()} ·"
                                )
                            ]
                            if dates.get(f"fixed_{key}"):
                                self.assertEqual(
                                    date_details[0]["value"],
                                    dates[f"fixed_{key}"],
                                )
                                self.assertIn(
                                    "Manual metadata", date_details[0]["label"]
                                )
                            elif dates.get(key):
                                self.assertIn(
                                    "CSV column", date_details[0]["label"]
                                )
                            else:
                                self.assertEqual(date_details, [])
                    heading, details = G._lookup(
                        7, "sea_ice_concentration", 1, 332, 2006, 12
                    )
                    self.assertIn("No observation", heading)
                    self.assertEqual(details, [])

    def test_invalid_manual_saved_mappings_are_errors_not_date_counters(self):
        for dates in (
            {"fixed_year": "2004"},
            {"fixed_month": "11"},
            {"year": "", "fixed_year": "10000"},
            {"month": "", "fixed_month": "1.5"},
        ):
            with (
                self.subTest(dates=dates),
                patch("app.states.overview_grid.rx.session") as factory,
            ):
                factory.return_value.__enter__.return_value = self.database(
                    mapping=MAPPING | dates
                )
                result = G._render("")
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["invalid_dates"], 0)
                self.assertEqual(result["invalid_coordinates"], 0)
                with self.assertRaises(ValueError):
                    G._lookup(7, "sea_ice_concentration", 1, 332, 2004, 11)

    def test_geographic_coordinates_empty_map_has_actionable_pixel_message(
        self,
    ):
        columns = ["Latitude", "Longitude", "Concentration"]
        mapping = {
            "coordinate_mode": "columns",
            "x_coordinate": "Latitude",
            "y_coordinate": "Longitude",
            "sea_ice_concentration": "Concentration",
            "fixed_year": "2004",
            "fixed_month": "11",
        }
        records = [["-39.36487", "-42.23257", "0"]] * 82120
        with patch("app.states.overview_grid.rx.session") as factory:
            factory.return_value.__enter__.return_value = self.database(
                records, mapping, columns
            )
            result = G._render("")
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["total"], 82120)
        self.assertEqual(result["period_rows"], 82120)
        self.assertEqual(result["invalid_coordinates"], 82120)
        self.assertEqual(result["invalid_dates"], 0)
        self.assertEqual(result["invalid_readings"], 0)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(result["valid"], 0)
        self.assertIn("Latitude/longitude are not pixel x/y", result["message"])
        self.assertIn(
            "x must be integer 1–316 and y integer 1–332", result["message"]
        )
        self.assertIn("exactly 104,912", result["message"])

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
