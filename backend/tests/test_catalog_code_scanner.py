"""Catalog-aware code scanner tests (F-A).

Recognizes real catalog codes that the shape-based regex can't (pure
numeric 764744, short alnum HDZWM2, spaced HDZ WM2) with ~zero false
positives — a token matches only if it equals a real catalog code.
"""

from __future__ import annotations

from app.services.catalog_code_scanner import scan_text_for_catalog_codes

# normalize(code) -> canonical; mirrors what the service builds from the catalog.
CATALOG = {"764744": "764744", "581239": "581239", "hdzwm2": "HDZWM2"}


def _by_code(rows):
    return {r["part_code"]: r for r in rows}


class TestCatalogScan:
    def test_pure_numeric_code_recovered(self):
        rows = scan_text_for_catalog_codes("764744 ... 2 adet", CATALOG)
        assert rows[0]["part_code"] == "764744"
        assert rows[0]["quantity"] == 2

    def test_spaced_variant_collapses_to_catalog_code(self):
        rows = scan_text_for_catalog_codes("HDZ WM2 1 qty", CATALOG)
        assert rows[0]["part_code"] == "HDZWM2"
        assert rows[0]["quantity"] == 1

    def test_english_qty_no_space(self):
        rows = scan_text_for_catalog_codes("764744 2qty", CATALOG)
        assert rows[0]["quantity"] == 2

    def test_full_three_line_rfq(self):
        text = "764744 ... 2 adet\n581239 ... 3 adet\nHDZWM2 ... 1 ADET"
        by = _by_code(scan_text_for_catalog_codes(text, CATALOG))
        assert by["764744"]["quantity"] == 2
        assert by["581239"]["quantity"] == 3
        assert by["HDZWM2"]["quantity"] == 1

    def test_no_false_positive_on_spec_table_line(self):
        # diameters / pressures / capacities must NOT be read as codes.
        line = "Türbinmetre (LF+2 HF) 2 G400 DN100 ANSI Class 600 30 Bar"
        assert scan_text_for_catalog_codes(line, CATALOG) == []

    def test_non_catalog_number_ignored(self):
        # 999999 isn't in the catalog -> not extracted (zero false positive).
        assert scan_text_for_catalog_codes("999999 5 adet", CATALOG) == []

    def test_missing_quantity_flagged_suspect(self):
        rows = scan_text_for_catalog_codes("764744 acil lazim", CATALOG)
        assert rows[0]["quantity"] == 1
        assert rows[0]["quantity_suspect"] is True

    def test_duplicate_code_deduped(self):
        rows = scan_text_for_catalog_codes("764744 2 adet\n764744 again", CATALOG)
        assert len(rows) == 1

    def test_empty_inputs(self):
        assert scan_text_for_catalog_codes("", CATALOG) == []
        assert scan_text_for_catalog_codes("764744", {}) == []
