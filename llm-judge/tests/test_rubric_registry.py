"""Tests for rubrics/registry.py."""

from __future__ import annotations

import pytest

from llm_judge.rubrics.registry import get_golden_type, get_rubric_content, get_rubric_name


class TestGetRubricName:
    # Exact filenames
    def test_full_summary_json(self):
        assert get_rubric_name("full_summary.json") == "full_summary"

    def test_split_document_summaries(self):
        assert (
            get_rubric_name("split_document_summaries.json")
            == "split_document_summaries_by_dates"
        )

    def test_sick_permits(self):
        assert get_rubric_name("sick_permits.json") == "sick_permits"

    def test_personal_details(self):
        assert get_rubric_name("personal_details.json") == "personal_details"

    def test_past_committees(self):
        assert get_rubric_name("past_committees.json") == "past_committees"

    # Parameterised patterns
    def test_page_pair(self):
        assert get_rubric_name("Page1<>Page2.json") == "same_document"

    def test_page_pair_large_numbers(self):
        assert get_rubric_name("Page10<>Page20.json") == "same_document"

    def test_medical_doc_numbered(self):
        assert get_rubric_name("medical_doc_3.json") == "medical_document"

    def test_medical_doc_numbered_large(self):
        assert get_rubric_name("medical_doc_123.json") == "medical_document"

    def test_medical_doc_validator(self):
        assert (
            get_rubric_name("medical_doc_validator_2.json") == "medical_document_validator"
        )

    def test_check_duplication(self):
        assert (
            get_rubric_name("check_duplication_1<>2.json") == "document_duplicate_check"
        )

    def test_check_duplication_large(self):
        assert (
            get_rubric_name("check_duplication_100<>200.json")
            == "document_duplicate_check"
        )

    # Dropped types now return None
    def test_findings_no_longer_mapped(self):
        assert get_rubric_name("findings.json") is None

    def test_final_summary_no_longer_mapped(self):
        assert get_rubric_name("final_summary.json") is None

    def test_classifier_no_longer_mapped(self):
        assert get_rubric_name("document_conditions_classifier_1.json") is None

    # Unknown
    def test_unknown_file(self):
        assert get_rubric_name("unknown_file.json") is None

    def test_partial_match_not_accepted(self):
        assert get_rubric_name("medical_doc_abc.json") is None


class TestGetGoldenType:
    """Golden type mirrors the rubric name (one golden set per filename type)."""

    def test_matches_rubric_name(self):
        assert get_golden_type("sick_permits.json") == "sick_permits"

    def test_matches_rubric_name_for_parameterised(self):
        assert (
            get_golden_type("medical_doc_validator_1.json") == "medical_document_validator"
        )

    def test_unknown_file_returns_none(self):
        assert get_golden_type("unknown_file.json") is None


class TestGetRubricContent:
    def test_loads_full_summary(self):
        content = get_rubric_content("full_summary")
        assert "Required Output Format" in content

    def test_raises_for_unknown_rubric(self):
        with pytest.raises(FileNotFoundError):
            get_rubric_content("nonexistent_rubric")

    def test_all_rubrics_have_output_format(self):
        rubric_names = [
            "full_summary",
            "split_document_summaries_by_dates",
            "sick_permits",
            "personal_details",
            "past_committees",
            "same_document",
            "medical_document",
            "medical_document_validator",
            "document_duplicate_check",
        ]
        for name in rubric_names:
            content = get_rubric_content(name)
            assert "Required Output Format" in content, (
                f"Rubric {name!r} is missing 'Required Output Format' section"
            )
            assert '"score"' in content, f"Rubric {name!r} is missing 'score' in output example"
