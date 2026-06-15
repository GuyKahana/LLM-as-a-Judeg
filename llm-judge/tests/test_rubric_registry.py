"""Tests for rubrics/registry.py."""

from __future__ import annotations

import pytest

from llm_judge.rubrics.registry import get_rubric_content, get_rubric_name


class TestGetRubricName:
    # Exact filenames → final_summary
    def test_final_summary_json(self):
        assert get_rubric_name("final_summary.json") == "final_summary"

    def test_full_summary_json(self):
        assert get_rubric_name("full_summary.json") == "final_summary"

    # document_summaries
    def test_split_document_summaries(self):
        assert get_rubric_name("split_document_summaries.json") == "document_summaries"

    def test_medical_doc_numbered(self):
        assert get_rubric_name("medical_doc_3.json") == "document_summaries"

    def test_medical_doc_numbered_large(self):
        assert get_rubric_name("medical_doc_123.json") == "document_summaries"

    # extraction_list
    def test_findings(self):
        assert get_rubric_name("findings.json") == "extraction_list"

    def test_surgeries(self):
        assert get_rubric_name("surgeries.json") == "extraction_list"

    def test_sick_permits(self):
        assert get_rubric_name("sick_permits.json") == "extraction_list"

    def test_incidents(self):
        assert get_rubric_name("incidents.json") == "extraction_list"

    def test_disabilities(self):
        assert get_rubric_name("disabilities.json") == "extraction_list"

    def test_adl_records(self):
        assert get_rubric_name("adl_records.json") == "extraction_list"

    def test_accident_details(self):
        assert get_rubric_name("accident_details.json") == "extraction_list"

    def test_clean_medications(self):
        assert get_rubric_name("clean_medications.json") == "extraction_list"

    # grouping_boundary
    def test_filter_diagnoses(self):
        assert get_rubric_name("filter_diagnoses.json") == "grouping_boundary"

    def test_merge_diagnoses(self):
        assert get_rubric_name("merge_diagnoses.json") == "grouping_boundary"

    def test_page_pair(self):
        assert get_rubric_name("Page1<>Page2.json") == "grouping_boundary"

    def test_page_pair_large_numbers(self):
        assert get_rubric_name("Page10<>Page20.json") == "grouping_boundary"

    # classifier
    def test_document_conditions_classifier(self):
        assert get_rubric_name("document_conditions_classifier_1.json") == "classifier"

    def test_diagnoses_by_date_classifier(self):
        assert get_rubric_name("diagnoses_by_date_classifier_5.json") == "classifier"

    def test_medical_doc_validator(self):
        assert get_rubric_name("medical_doc_validator_2.json") == "classifier"

    # duplicate_check
    def test_check_duplication(self):
        assert get_rubric_name("check_duplication_1<>2.json") == "duplicate_check"

    def test_check_duplication_large(self):
        assert get_rubric_name("check_duplication_100<>200.json") == "duplicate_check"

    # personal_committee
    def test_personal_details(self):
        assert get_rubric_name("personal_details.json") == "personal_committee"

    def test_past_committees(self):
        assert get_rubric_name("past_committees.json") == "personal_committee"

    # Unknown
    def test_unknown_file(self):
        assert get_rubric_name("unknown_file.json") is None

    def test_random_filename(self):
        assert get_rubric_name("some_random_log_20240101.json") is None

    def test_partial_match_not_accepted(self):
        # Should not match medical_doc_\d+ because of extra text
        assert get_rubric_name("medical_doc_abc.json") is None


class TestGetRubricContent:
    def test_loads_final_summary(self):
        content = get_rubric_content("final_summary")
        assert "completeness" in content.lower()
        assert "Required Output Format" in content

    def test_loads_extraction_list(self):
        content = get_rubric_content("extraction_list")
        assert "recall" in content.lower()

    def test_loads_duplicate_check(self):
        content = get_rubric_content("duplicate_check")
        assert "duplicate" in content.lower()

    def test_raises_for_unknown_rubric(self):
        with pytest.raises(FileNotFoundError):
            get_rubric_content("nonexistent_rubric")

    def test_all_rubrics_have_output_format(self):
        rubric_names = [
            "final_summary", "document_summaries", "extraction_list",
            "classifier", "grouping_boundary", "duplicate_check", "personal_committee",
        ]
        for name in rubric_names:
            content = get_rubric_content(name)
            assert "Required Output Format" in content, (
                f"Rubric {name!r} is missing 'Required Output Format' section"
            )
            assert '"score"' in content, f"Rubric {name!r} is missing 'score' in output example"
