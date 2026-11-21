"""Regression tests for prediction dataset mapping and monthly accuracy."""

import json
import unittest

from app.states.uploaded_data import UploadedData


class PredictionComparisonTests(unittest.TestCase):
    def test_prediction_mapping_requires_distinct_existing_columns(self):
        """Reject missing and duplicate prediction/date source columns."""
        columns = ["predicted_sic", "year", "month"]
        mapping = {
            "prediction": "predicted_sic",
            "year": "year",
            "month": "month",
        }
        self.assertEqual(
            UploadedData._validate_prediction_mapping(columns, mapping),
            mapping,
        )
        with self.assertRaisesRegex(ValueError, "three different columns"):
            UploadedData._validate_prediction_mapping(
                columns, mapping | {"month": "year"}
            )
        with self.assertRaisesRegex(ValueError, "available prediction"):
            UploadedData._validate_prediction_mapping(
                columns, mapping | {"prediction": "missing"}
            )

    def test_monthly_means_skip_invalid_or_out_of_range_values(self):
        """Use valid concentrations and dates when computing monthly means."""
        columns = ["prediction", "year", "month"]
        rows = [
            json.dumps(["70", "2024", "1"]),
            json.dumps(["90", "2024", "1"]),
            json.dumps(["101", "2024", "1"]),
            json.dumps(["not numeric", "2024", "1"]),
            json.dumps(["0", "2024", "2"]),
            json.dumps(["55", "2024", "13"]),
        ]
        monthly = UploadedData._monthly_measurements(
            rows,
            columns,
            {"prediction": "prediction", "year": "year", "month": "month"},
            "prediction",
        )
        self.assertEqual(monthly, {(2024, 1): 80.0, (2024, 2): 0.0})

    def test_accuracy_uses_only_matched_monthly_means(self):
        """Average bounded percentage-point accuracy across paired months."""
        rows, accuracy = UploadedData._compare_monthly_values(
            {(2024, 1): 80.0, (2024, 2): 0.0, (2024, 3): 25.0},
            {(2024, 1): 70.0, (2024, 2): 100.0},
        )
        self.assertEqual([row["period"] for row in rows], ["2024-01", "2024-02"])
        self.assertEqual([row["accuracy"] for row in rows], [90.0, 0.0])
        self.assertEqual(accuracy, 45.0)
        self.assertEqual(
            UploadedData._compare_monthly_values({}, {(2024, 1): 80.0}),
            ([], None),
        )


if __name__ == "__main__":
    unittest.main()
