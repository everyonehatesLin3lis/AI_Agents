"""UI tests with Streamlit's AppTest: the real app script, no browser.

No LLM key is set in tests (see conftest), so the app runs in its rule-only mode. That
is enough to test the walking skeleton: Terraform in, findings shown.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from evals.dataset_loader import load_samples

APP = str(Path(__file__).resolve().parents[2] / "ui" / "app.py")
SAMPLE = next(s for s in load_samples() if s.file == "vulnerable/gcs_public.tf")


@pytest.fixture
def app(tmp_path, monkeypatch) -> AppTest:
    monkeypatch.setenv("REVIEW_DATA_DIR", str(tmp_path))
    return AppTest.from_file(APP, default_timeout=60).run()


def page_text(app: AppTest) -> str:
    elements = [*app.markdown, *app.subheader, *app.error, *app.warning, *app.info, *app.success]
    return "\n".join(str(element.value) for element in elements)


def review(app: AppTest, terraform: str) -> AppTest:
    app.text_area(key="terraform_(none)").set_value(terraform)
    return app.button(key="review").click().run()


def test_app_starts_without_errors(app):
    assert not app.exception
    assert app.title[0].value == "GCP Infra Review Agent"


def test_terraform_in_findings_shown(app):
    review(app, SAMPLE.terraform)

    text = page_text(app)
    assert not app.exception
    assert "GCS-001" in text
    assert "CRITICAL" in text
    assert "4 security finding(s)" in text
    assert app.metric[1].value == "$2.00"


def test_non_terraform_input_shows_a_clear_error(app):
    review(app, "gcloud compute instances create vm-1")

    assert not app.exception
    assert "does not look like Terraform" in app.error[0].value


def test_review_waits_for_feedback_then_finishes(app):
    review(app, SAMPLE.terraform)
    assert any("Your feedback" in str(s.value) for s in app.subheader)

    finish = next(b for b in app.button if b.label == "Finish review")
    finish.click().run()

    assert not app.exception
    assert "saved to this project's history" in page_text(app)


def test_developer_settings_are_in_their_own_section(app):
    labels = [expander.label for expander in app.sidebar.expander]

    assert "Developer" in labels
    assert "Project memory" in labels
    assert app.sidebar.text_input(key="dev_model").value  # model is configurable here
