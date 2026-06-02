"""Phase-3 tests: spreadsheet quantity integrity (audit Q1/Q2/Q5).

The pre-fix ``extract_rows_as_parts`` took "the first integer ≤ 9999 in
the row" as the quantity. That:
  * captured the line-number column ("1 | code | desc | 5" -> qty 1)  [Q1]
  * silently coerced bulk orders ≥ 10 000 to 1                        [Q2]
"""

from __future__ import annotations

from app.services.email_attachment_parser import extract_rows_as_parts


class TestHeaderAwareQuantity:
    def test_line_number_column_is_not_taken_as_quantity(self):
        rows = [
            ["#", "Code", "Description", "Qty", "Unit Price"],
            ["1", "C7061A1012", "Flame detector", "5", "1200"],
            ["2", "RM7895A1014", "Burner controller", "2", "3400"],
        ]
        parts = {p["part_code"]: p for p in extract_rows_as_parts(rows)}
        assert parts["C7061A1012"]["quantity"] == 5  # not 1 (line number)
        assert parts["RM7895A1014"]["quantity"] == 2

    def test_turkish_headers(self):
        rows = [
            ["Sıra", "Malzeme Kodu", "Açıklama", "Adet"],
            ["1", "C7061A1012", "Alev dedektoru", "7"],
        ]
        parts = extract_rows_as_parts(rows)
        assert parts[0]["quantity"] == 7

    def test_bulk_quantity_over_10k_preserved(self):
        rows = [
            ["Code", "Description", "Qty"],
            ["C7061A1012", "Flame detector", "12000"],
        ]
        parts = extract_rows_as_parts(rows)
        assert parts[0]["quantity"] == 12000  # not clamped to 1
        assert parts[0]["quantity_suspect"] is False

    def test_thousands_separator_quantity(self):
        rows = [
            ["Code", "Qty"],
            ["C7061A1012", "12.000"],
        ]
        parts = extract_rows_as_parts(rows)
        assert parts[0]["quantity"] == 12000


class TestNoHeaderFallback:
    def test_leading_line_number_skipped(self):
        # No recognizable header row; the leading "1" is a line number.
        rows = [
            ["1", "C7061A1012", "Flame detector", "5", "1200"],
        ]
        parts = extract_rows_as_parts(rows)
        assert parts[0]["part_code"] == "C7061A1012"
        assert parts[0]["quantity"] == 5

    def test_missing_quantity_flagged_suspect_not_silent_one(self):
        rows = [
            ["Code", "Description", "Qty"],
            ["C7061A1012", "Flame detector", ""],
        ]
        parts = extract_rows_as_parts(rows)
        assert parts[0]["quantity"] == 1
        assert parts[0]["quantity_suspect"] is True


class TestRegressionHappyPath:
    def test_simple_code_desc_qty(self):
        rows = [
            ["Code", "Desc", "Qty"],
            ["C7061A1012", "Flame detector", 5],
            ["RM7895A1014", "Burner controller", 2],
        ]
        parts = extract_rows_as_parts(rows)
        codes = {p["part_code"] for p in parts}
        assert codes == {"C7061A1012", "RM7895A1014"}
        by_code = {p["part_code"]: p for p in parts}
        assert by_code["C7061A1012"]["quantity"] == 5
