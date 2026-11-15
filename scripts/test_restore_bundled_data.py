import reflex as rx

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from antarctic_sea_ice_dashboard.models import UploadedDataset
from antarctic_sea_ice_dashboard.states.antarctic_globe import (
    MAX_ROWS as GLOBE_MAX_ROWS,
)
from antarctic_sea_ice_dashboard.states.snapshot_comparison import (
    MAX_ROWS as COMPARISON_MAX_ROWS,
    SnapshotComparison,
)
from antarctic_sea_ice_dashboard.states.uploaded_data import MAX_ROWS
from scripts.restore_bundled_data import (
    infer_snapshot,
    restore_file,
    suggested_mapping,
)


class SnapshotInferenceTests(unittest.TestCase):
    def test_exact_six_digit_prefix_and_normalized_dates(self):
        for filename, year, month in (
            ("200411_sea_ice_concentration_NSIDC_grid.csv", "2004", "11"),
            ("200605_SST_hadl_NSIDC_grid.csv", "2006", "5"),
            ("201605_10m_wind_speed.csv", "2016", "5"),
            ("201609_v_wind.csv", "2016", "9"),
            ("202005_sea_ice_concentration_NSIDC_grid.csv", "2020", "5"),
            ("202009_sea_ice_concentration_NSIDC_grid.csv", "2020", "9"),
            ("202209_all_pred_posterior_seed_52.csv", "2022", "9"),
            ("202210_SST_hadl_NSIDC_grid.csv", "2022", "10"),
            ("202211_SST_hadl_NSIDC_grid.csv", "2022", "11"),
            ("202212_SST_hadl_NSIDC_grid.csv", "2022", "12"),
            ("202309_all_pred_posterior_seed_52.csv", "2023", "9"),
            ("202309_sea_ice_concentration_NSIDC_grid.csv", "2023", "9"),
            ("000101_snapshot.csv", "1", "1"),
        ):
            with self.subTest(filename=filename):
                self.assertEqual(
                    infer_snapshot(Path(filename)),
                    {"fixed_year": year, "fixed_month": month},
                )

    def test_rejects_nonexact_prefix_or_invalid_calendar_metadata(self):
        for filename in (
            "2023091_data.csv",
            "20230901_data.csv",
            "20239_data.csv",
            "x202309_data.csv",
            "2023_09_data.csv",
            "202300_data.csv",
            "202313_data.csv",
            "000009_data.csv",
            "２０２３０９_data.csv",
        ):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                infer_snapshot(Path(filename))


class SupportedMappingTests(unittest.TestCase):
    def test_supported_measurements_activate_only_normalized_mapping(self):
        dates = {"fixed_year": "2016", "fixed_month": "5"}
        for column, field in (
            ("Concentration", "sea_ice_concentration"),
            ("SST", "sea_surface_temperature"),
            ("wind_speed", "wind_speed"),
        ):
            with self.subTest(column=column):
                mapping, active = suggested_mapping(
                    ["Latitude", "Longitude", column], 347040, dates
                )
                self.assertTrue(active)
                self.assertEqual(mapping[field], column)
                self.assertEqual(mapping["latitude"], "Latitude")
                self.assertEqual(mapping["fixed_month"], "5")

    def test_unsupported_columns_or_missing_coordinates_remain_inactive(self):
        dates = {"fixed_year": "2023", "fixed_month": "9"}
        for columns in (
            ["Latitude", "Longitude", "v_wind"],
            [
                "Longitude",
                "Latitude",
                "Prob_1_previous_year",
                "Prob_Not_1_previous_year",
                "Post_Prob_1",
                "Post_Prob_Not_1",
                "Post_Pred_class",
            ],
            [
                "Longitude",
                "Latitude",
                "Sea_1_extent",
                "Prob_1",
                "Prob_Not_1",
                "Pred_class",
            ],
            ["Latitude", "wind_speed"],
        ):
            with self.subTest(columns=columns):
                mapping, active = suggested_mapping(columns, 347040, dates)
                self.assertFalse(active)
                self.assertEqual(mapping, dates)
                self.assertIsNot(mapping, dates)


class RestorationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "201605_10m_wind_speed.csv"
        self.session = MagicMock()
        self.session.get_bind.return_value.dialect.name = "postgresql"
        self.session.scalar.return_value = None
        self.session.flush.side_effect = self.assign_id
        self.session_patch = patch.object(rx, "session")
        factory = self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        factory.return_value.__enter__.return_value = self.session

    def assign_id(self):
        self.session.add.call_args.args[0].id = 42

    def batch_calls(self):
        return [
            call
            for call in self.session.execute.call_args_list
            if len(call.args) == 2
        ]

    def test_import_batches_preserve_every_string_and_existing_edits_on_rerun(
        self,
    ):
        self.path.write_bytes(
            b"Latitude,Longitude,wind_speed\n" + b"-30,-180,007.50\n" * 2001
        )
        first = restore_file(self.path)
        self.assertEqual(first["status"], "inserted")
        self.assertEqual(first["inserted_rows"], 2001)
        dataset = self.session.add.call_args.args[0]
        self.assertEqual(dataset.name, self.path.stem)
        self.assertEqual(dataset.original_filename, self.path.name)
        self.assertEqual(dataset.row_count, 2001)
        self.assertTrue(dataset.map_layer_active)
        batches = self.batch_calls()
        self.assertEqual(
            [len(call.args[1]) for call in batches], [1000, 1000, 1]
        )
        records = [record for call in batches for record in call.args[1]]
        self.assertEqual(
            [record["row_position"] for record in records], list(range(2001))
        )
        self.assertEqual(
            json.loads(records[-1]["cell_values_json"]),
            ["-30", "-180", "007.50"],
        )
        self.assertEqual(
            json.loads(dataset.map_mapping_json)["fixed_month"], "5"
        )
        dataset.name = "User renamed dataset"
        dataset.map_mapping_json = '{"user": "edited"}'
        dataset.map_layer_active = False
        self.session.scalar.return_value = dataset
        self.path.unlink()
        with patch.object(
            Path,
            "open",
            side_effect=AssertionError("Must not reread existing files"),
        ):
            second = restore_file(self.path)
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(second["inserted_rows"], 0)
        self.assertFalse(second["active"])
        self.assertEqual(dataset.name, "User renamed dataset")
        self.assertEqual(dataset.map_mapping_json, '{"user": "edited"}')
        self.assertEqual(len(self.batch_calls()), 3)
        self.session.add.assert_called_once()

    def test_unsupported_raw_columns_are_saved_unchanged_with_date_only(self):
        self.path = self.path.with_name("202309_all_pred_posterior_seed_52.csv")
        self.path.write_bytes(
            b"Longitude,Latitude,Sea_1_extent,Prob_1,Pred_class\n-42,-39,001,0.014910913,01\n"
        )
        result = restore_file(self.path)
        self.assertFalse(result["active"])
        dataset = self.session.add.call_args.args[0]
        self.assertEqual(
            json.loads(dataset.column_names_json),
            ["Longitude", "Latitude", "Sea_1_extent", "Prob_1", "Pred_class"],
        )
        self.assertEqual(
            json.loads(dataset.map_mapping_json),
            {"fixed_year": "2023", "fixed_month": "9"},
        )
        record = self.batch_calls()[0].args[1][0]
        self.assertEqual(
            json.loads(record["cell_values_json"]),
            ["-42", "-39", "001", "0.014910913", "01"],
        )

    def test_existing_filename_is_skipped_before_validation(self):
        existing = UploadedDataset(
            id=7,
            name="Edited",
            original_filename="invalid.csv",
            map_layer_active=False,
        )
        self.session.scalar.return_value = existing
        result = restore_file(self.path.with_name("invalid.csv"))
        self.assertEqual(result["dataset_id"], 7)
        self.assertEqual(result["status"], "skipped")
        self.session.add.assert_not_called()
        self.assertEqual(self.batch_calls(), [])

    def test_insert_failure_leaves_transaction_with_exception_for_rollback(
        self,
    ):
        self.path.write_bytes(b"Latitude,Longitude,wind_speed\n-30,-180,1\n")

        def fail_batch(*args):
            if len(args) == 2:
                raise RuntimeError("simulated batch failure")

        self.session.execute.side_effect = fail_batch
        with (
            self.assertLogs(level="ERROR"),
            self.assertRaisesRegex(RuntimeError, "batch failure"),
        ):
            restore_file(self.path)
        exit_args = self.session.begin.return_value.__exit__.call_args.args
        self.assertIs(exit_args[0], RuntimeError)
        self.session.commit.assert_not_called()

    def test_invalid_new_file_inserts_nothing(self):
        self.path.write_bytes(b"Latitude,Longitude,wind_speed\n-30,1\n")
        with self.assertLogs(level="ERROR"), self.assertRaises(ValueError):
            restore_file(self.path)
        self.session.add.assert_not_called()
        self.assertEqual(self.batch_calls(), [])


class LargeLayerTests(unittest.TestCase):
    def test_shared_limit_and_comparison_consumes_all_wind_rows(self):
        self.assertEqual(MAX_ROWS, 400000)
        self.assertEqual(GLOBE_MAX_ROWS, MAX_ROWS)
        self.assertEqual(COMPARISON_MAX_ROWS, MAX_ROWS)
        session = MagicMock()
        session.execute.return_value = (
            ('["-30", "-180", "7.5"]',) for _ in range(347040)
        )
        summary = {"id": 1, "name": "Full wind layer"}
        mapping = {
            "latitude": "Latitude",
            "longitude": "Longitude",
            "wind_speed": "wind_speed",
        }
        mean, count, files, bins = SnapshotComparison._summarize_group(
            session,
            [(summary, mapping, ["Latitude", "Longitude", "wind_speed"])],
            "wind_speed",
        )
        self.assertEqual(count, 347040)
        self.assertEqual(files, 1)
        self.assertEqual(mean, 7.5)
        self.assertEqual(sum(len(values) for values in bins.values()), 347040)


if __name__ == "__main__":
    unittest.main()
