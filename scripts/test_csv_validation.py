import reflex as rx
import unittest

from app.states.uploaded_data import UploadedData, MAX_BYTES, MAX_ROWS


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
            ("columns.csv", ",".join(f"c{i}" for i in range(101)).encode()),
        ]
        for filename, data in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    UploadedData._parse_csv(filename, data)


if __name__ == "__main__":
    unittest.main()
