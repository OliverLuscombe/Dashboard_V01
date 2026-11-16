"""Tests for same-snapshot spatial prediction accuracy."""

import unittest
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from antarctic_sea_ice_dashboard.states.model_insights import (
    PredictionInsights,
)
from antarctic_sea_ice_dashboard.states.uploaded_data import UploadedData


class PredictionAccuracyTests(unittest.TestCase):
    def test_prediction_mapping_is_model_only_and_requires_snapshot_dates(self):
        columns = ["Latitude", "Longitude", "Prediction"]
        mapping = {
            "latitude": "Latitude",
            "longitude": "Longitude",
            "prediction": "Prediction",
            "fixed_year": "2023",
            "fixed_month": "9",
        }
        source = SimpleNamespace(
            id=1,
            name="Prediction",
            original_filename="prediction.csv",
            row_count=1,
            column_names_json=json.dumps(columns),
            map_mapping_json=json.dumps(mapping),
            map_layer_active=False,
            created_at=datetime.now(UTC),
        )
        summary = UploadedData._dataset_summary(source)
        self.assertFalse(summary["map_ready"])
        self.assertTrue(summary["model_ready"])
        self.assertTrue(summary["is_prediction"])
        self.assertEqual(summary["group_key"], "2023-09")

    def test_accuracy_uses_only_matching_locations_and_monthly_snapshot_data(self):
        prediction = {
            (-70.0, 10.0): (160.0, 2),
            (-71.0, 11.0): (20.0, 1),
        }
        observations = {
            (-70.0, 10.0): (140.0, 2),
            (-72.0, 12.0): (50.0, 1),
        }
        accuracy, matched = PredictionInsights._score(
            prediction, observations
        )
        self.assertEqual(accuracy, 90.0)
        self.assertEqual(matched, 1)

    def test_accuracy_is_bounded_and_missing_matches_are_unavailable(self):
        accuracy, matched = PredictionInsights._score(
            {(-70.0, 10.0): (100.0, 1)},
            {(-70.0, 10.0): (0.0, 1)},
        )
        self.assertEqual((accuracy, matched), (0.0, 1))
        self.assertEqual(PredictionInsights._score({}, {}), (None, 0))

    def test_numeric_parser_rejects_nonfinite_and_non_numeric_values(self):
        self.assertEqual(PredictionInsights._number("12.5"), 12.5)
        for value in ("", "NA", "NaN", "inf", "101e999"):
            with self.subTest(value=value):
                self.assertIsNone(PredictionInsights._number(value))


if __name__ == "__main__":
    unittest.main()
