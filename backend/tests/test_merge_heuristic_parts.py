"""Phase-4 tests: heuristic-merge correctness (audit Q3/Q4).

Pre-fix ``_merge_heuristic_parts`` deduped by ``code.strip().upper()`` (not
normalized), so a hyphen variant double-counted the part, and on a
body/attachment quantity conflict the attachment value was silently
dropped.
"""

from __future__ import annotations

from app.services.email_processing_service import _merge_heuristic_parts


class TestNormalizedDedup:
    def test_hyphen_variant_is_one_line_not_two(self):
        parsed = {"parts": [{"part_code": "C7061A1012", "quantity": 5}]}
        heuristic = [{"part_code": "C7061-A1012", "quantity": 5}]
        result = _merge_heuristic_parts(parsed, heuristic)
        assert len(result["parts"]) == 1  # not double-counted

    def test_distinct_codes_both_kept(self):
        parsed = {"parts": [{"part_code": "C7061A1012", "quantity": 5}]}
        heuristic = [{"part_code": "RM7895A1014", "quantity": 2}]
        result = _merge_heuristic_parts(parsed, heuristic)
        codes = {p["part_code"] for p in result["parts"]}
        assert codes == {"C7061A1012", "RM7895A1014"}
        assert result["is_spare_part_request"] is True


class TestQuantityConflict:
    def test_conflict_is_flagged_and_both_values_surfaced(self):
        parsed = {"parts": [{"part_code": "C7061A1012", "quantity": 3}]}
        heuristic = [{"part_code": "C7061-A1012", "quantity": 10}]
        result = _merge_heuristic_parts(parsed, heuristic)
        part = result["parts"][0]
        assert part["quantity_suspect"] is True
        assert part["quantity_conflict"] == {"body": 3, "attachment": 10}
        # original body quantity is preserved, not silently overwritten
        assert part["quantity"] == 3

    def test_matching_quantities_no_conflict_flag(self):
        parsed = {"parts": [{"part_code": "C7061A1012", "quantity": 5}]}
        heuristic = [{"part_code": "C7061A1012", "quantity": 5}]
        result = _merge_heuristic_parts(parsed, heuristic)
        assert "quantity_conflict" not in result["parts"][0]
        assert "quantity_suspect" not in result["parts"][0]


class TestNoHeuristicRows:
    def test_empty_heuristic_returns_unchanged(self):
        parsed = {"parts": [{"part_code": "C7061A1012", "quantity": 5}]}
        assert _merge_heuristic_parts(parsed, []) is parsed
