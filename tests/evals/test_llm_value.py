from evals.dataset_loader import load_samples
from evals.llm_value import (
    build,
    config_terms,
    enriched_rows,
    facts_by_resource,
    review_without_llm,
    split_advice,
    terms_named,
)

FACTS = {
    "settings.tier": "db-custom-2-7680",
    "settings.availability_type": "REGIONAL",
    "settings.disk_size": 100,
    "location": "US",
    "initial_node_count": 1,
    "scheduling.preemptible": True,
    "has_lifecycle_rule": False,
}
USER_INPUT = (
    "Review this configuration.\n"
    'Resources: [{"resource": "google_sql_database_instance.main", "service": "cloud_sql", '
    '"facts": {"settings.tier": "db-custom-2-7680", "settings.availability_type": "REGIONAL"}}]'
)


def test_config_terms_are_the_values_and_the_missing_blocks_not_the_noise():
    assert config_terms(FACTS) == ["db-custom-2-7680", "REGIONAL", "100", "lifecycle rule"]


def test_a_text_that_names_a_value_of_the_configuration_is_specific():
    text = "Change availability_type from regional to ZONAL; 100 GB is enough."

    assert terms_named(text, FACTS) == ["REGIONAL", "100"]


def test_generic_advice_names_nothing_from_the_configuration():
    assert terms_named("Monitor CPU and memory usage and right-size the tier.", FACTS) == []


def test_a_value_inside_a_longer_word_or_number_does_not_count():
    assert terms_named("About 1000 requests hit db-custom-2-7680-old.", FACTS) == []


def test_saved_text_is_split_and_matched_to_the_facts_of_its_own_resource():
    record = {
        "model": "m",
        "config": "full",
        "file": "vulnerable/sql_open.tf",
        "judge_input": {
            "user_input": USER_INPUT,
            "advisory_text": "A regional instance.\n"
            "google_sql_database_instance.main: HA doubles cost. Switch REGIONAL to ZONAL.\n"
            "google_sql_database_instance.main: Maybe oversized. "
            "Suggestion (no documentation source): right-size it.",
        },
    }

    (row,) = enriched_rows([record, {"model": "m", "config": "no_rag", "judge_input": None}])

    assert facts_by_resource(USER_INPUT)["google_sql_database_instance.main"]
    assert split_advice("s\na\nb") == ("s", ["a", "b"])
    assert row["summary_terms"] == ["REGIONAL"]
    assert [r["terms"] for r in row["recommendations"]] == [["REGIONAL"], []]
    assert [r["has_source"] for r in row["recommendations"]] == [True, False]


def test_without_an_llm_the_report_has_findings_and_cost_but_no_advice(make_deps, monkeypatch):
    samples = [s for s in load_samples() if s.file == "vulnerable/sql_open.tf"]
    deps = make_deps(None)
    monkeypatch.setattr("evals.llm_value.deterministic_deps", lambda settings, memory: deps)

    without_llm = review_without_llm(samples, deps.settings)
    comparison = {
        "meta": {"git": {"commit": "abc"}, "models": [], "judge_model": None},
        "records": [],
    }
    result = build("x_llm.json", comparison, without_llm)["deterministic"]

    assert result["security_findings"] == 5
    assert result["reviews_with_cost_estimate"] == 1
    assert result["recommendations"] == 0
    assert result["summaries_written"] == 0
