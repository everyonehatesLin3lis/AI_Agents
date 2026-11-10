"""Streamlit UI for the GCP Infra Review Agent.

Run with:  uv run streamlit run ui/app.py

Layout:
- Main area: paste or upload Terraform, run the review, read the report, give feedback.
- Sidebar "Project memory": budget, region and preferences remembered per project.
- Sidebar "Developer": model, temperature and prompt additions. Kept apart from the
  main flow because a normal user should never need it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # `streamlit run ui/app.py` puts ui/ on the path, not the root
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from agent.config import Settings  # noqa: E402
from agent.deps import default_deps  # noqa: E402
from agent.llm import resolve_provider  # noqa: E402
from agent.report import render_markdown  # noqa: E402
from agent.runner import ReviewSession  # noqa: E402
from agent.state import ReviewReport  # noqa: E402
from evals.dataset_loader import DATASET_DIR, read_terraform  # noqa: E402
from memory.store import FeedbackAction, FeedbackItem, ProjectConstraints  # noqa: E402
from tools.models import Category, Finding  # noqa: E402
from tools.tf_parser import MAX_INPUT_BYTES, TerraformInputError  # noqa: E402

REGIONS = ["us-central1", "us-east1", "us-west1", "europe-west1", "europe-west3",
           "europe-west4", "europe-north1", "asia-southeast1"]  # fmt: skip
SEVERITY_ICONS = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}
NO_FEEDBACK = "No feedback"
FEEDBACK_CHOICES = {NO_FEEDBACK: None, "Helpful": FeedbackAction.HELPFUL,
                    "Not relevant for this project": FeedbackAction.DISMISS}  # fmt: skip


@st.cache_resource(show_spinner=False)
def get_session(settings_json: str) -> ReviewSession:
    """One `ReviewSession` per distinct settings, kept across Streamlit reruns."""
    return ReviewSession(default_deps(Settings.model_validate_json(settings_json)))


# ------------------------------------------------------------------- sidebar


def developer_settings() -> Settings:
    base = Settings.from_env()
    with st.sidebar.expander("Developer", expanded=False):
        st.caption("Settings for developers. They do not change the security rules.")
        provider = resolve_provider()
        st.write(f"LLM provider: **{provider.name if provider else 'not configured'}**")
        model = st.text_input("Model", base.model, key="dev_model")
        send_temperature = st.checkbox("Send temperature", base.temperature is not None)
        temperature = st.slider("Temperature", 0.0, 1.0, base.temperature or 0.0, 0.1)
        use_rag = st.checkbox("Use documentation search (RAG)", base.use_rag, key="dev_rag")
        max_rewrites = st.slider("Max query rewrites", 0, 2, base.max_rewrites)
        extra = st.text_area(
            "Extra instructions for the report writer", base.extra_instructions, key="dev_extra"
        )
    return base.model_copy(
        update={
            "model": model.strip() or base.model,
            "temperature": temperature if send_temperature else None,
            "use_rag": use_rag,
            "max_rewrites": max_rewrites,
            "extra_instructions": extra,
        }
    )


def project_memory(session: ReviewSession, project_id: str) -> None:
    saved = session.deps.store.get_constraints(project_id)
    with st.sidebar.expander("Project memory", expanded=False):
        st.caption("Remembered for this project and used in every review.")
        with st.form("constraints"):
            budget = st.number_input(
                "Monthly budget (USD, 0 = none)", 0.0, value=saved.budget_monthly_usd or 0.0
            )
            options = ["(not set)", *REGIONS]
            index = options.index(saved.region) if saved.region in options else 0
            region = st.selectbox("Default region", options, index=index)
            preferences = st.text_area(
                "Preferences (one per line)", "\n".join(saved.preferences), max_chars=500
            )
            if st.form_submit_button("Save"):
                session.deps.store.save_constraints(
                    project_id,
                    ProjectConstraints(
                        budget_monthly_usd=budget or None,
                        region=None if region == "(not set)" else region,
                        preferences=[p.strip() for p in preferences.splitlines() if p.strip()],
                    ),
                )
                st.success("Saved.")


# ---------------------------------------------------------------------- input


def sample_files() -> dict[str, Path]:
    return {
        str(p.relative_to(DATASET_DIR).as_posix()): p for p in sorted(DATASET_DIR.rglob("*.tf"))
    }


def terraform_input() -> str:
    samples = sample_files()
    choice = st.selectbox("Start from a sample (optional)", ["(none)", *samples], key="sample")
    uploaded = st.file_uploader("Upload a .tf file", type=["tf"])
    default = read_terraform(samples[choice]) if choice != "(none)" else ""
    if uploaded is not None:
        if uploaded.size > MAX_INPUT_BYTES:
            st.error(f"The file is larger than {MAX_INPUT_BYTES // 1000} KB.")
        else:
            default = uploaded.getvalue().decode("utf-8-sig", errors="replace")
    return st.text_area("Terraform", default, height=260, key=f"terraform_{choice}")


# --------------------------------------------------------------------- report


def show_finding(finding: Finding) -> None:
    icon = SEVERITY_ICONS[finding.severity.value]
    rule = f"{finding.rule_id} · " if finding.rule_id else ""
    note = " · deprioritized by your earlier feedback" if finding.deprioritized else ""
    with st.container(border=True):
        st.markdown(
            f"{icon} **{finding.severity.value.upper()}** · {rule}`{finding.resource}`{note}"
        )
        st.markdown(f"**Issue:** {finding.issue}")
        st.markdown(f"**Recommendation:** {finding.recommendation}")
        if finding.estimated_savings:
            st.markdown(f"**Estimated savings:** ${finding.estimated_savings:,.2f}/month")
        if finding.source_url:
            st.markdown(f"**Source:** {finding.source_url}")
        else:
            st.caption("No documentation source: treat this as a suggestion, not a fact.")


def show_metrics(report: ReviewReport) -> None:
    usage = report.usage
    cost = report.cost_estimate
    columns = st.columns(5)
    columns[0].metric("Findings", len(report.findings))
    columns[1].metric("Est. cost / month", f"${cost.total_monthly_usd:,.2f}" if cost else "n/a")
    columns[2].metric("LLM tokens", f"{usage.input_tokens + usage.output_tokens:,}")
    columns[3].metric("LLM cost", "n/a" if usage.cost_usd is None else f"${usage.cost_usd:.4f}")
    columns[4].metric("Time", f"{report.timings.get('total', 0):.1f} s")


def show_cost(report: ReviewReport) -> None:
    cost = report.cost_estimate
    if cost is None:
        st.info("No cost estimate is available.")
        return
    st.table(
        [
            {
                "Resource": line.resource,
                "USD / month": f"{line.monthly_usd:,.2f}" if line.priced else "not priced",
                "Assumptions": " ".join(line.assumptions),
            }
            for line in cost.lines
        ]
    )
    for note in cost.notes:
        st.caption(note)


def show_run_details(report: ReviewReport) -> None:
    usage = report.usage
    st.write(
        f"Model **{report.model}** · {usage.llm_calls} LLM call(s) · "
        f"{usage.input_tokens:,} input and {usage.output_tokens:,} output tokens"
    )
    st.table(
        [{"Step": name, "Seconds": f"{seconds:.3f}"} for name, seconds in report.timings.items()]
    )
    if report.sources:
        st.write("Sources cited:")
        for url in report.sources:
            st.markdown(f"- {url}")


def show_report(report: ReviewReport) -> None:
    st.subheader(report.headline)
    if report.status == "failed":
        st.error(report.summary)
        return
    st.write(report.summary)
    for warning in report.warnings:
        st.warning(warning)
    show_metrics(report)
    security = [f for f in report.findings if f.category == Category.SECURITY]
    advice = [f for f in report.findings if f.category != Category.SECURITY]
    tabs = st.tabs(
        [
            f"Security ({len(security)})",
            f"Cost and sizing ({len(advice)})",
            "Cost estimate",
            "Run details",
        ]
    )
    with tabs[0]:
        st.caption("Decided by fixed rules. Feedback cannot hide or downgrade these.")
        for finding in security:
            show_finding(finding)
        if not security:
            st.success("The rule checks found no security problems.")
    with tabs[1]:
        for finding in advice:
            show_finding(finding)
        if not advice:
            st.info("No cost or sizing recommendations.")
    with tabs[2]:
        show_cost(report)
    with tabs[3]:
        show_run_details(report)
    if report.unsupported_resources:
        st.info("Not reviewed (unsupported type): " + ", ".join(report.unsupported_resources))
    st.download_button("Download report (Markdown)", render_markdown(report), "gcp-review.md")


def feedback_form(session: ReviewSession, report: ReviewReport) -> None:
    advice = [f for f in report.findings if f.category != Category.SECURITY]
    st.divider()
    st.subheader("Your feedback")
    st.caption(
        "Feedback is remembered for this project. It can lower the priority of cost and "
        "sizing suggestions. It never changes security findings."
    )
    with st.form("feedback"):
        answers: list[tuple[Finding, str, str]] = []
        for index, finding in enumerate(advice):
            st.markdown(f"`{finding.resource}`: {finding.issue}")
            choice = st.radio("Feedback", list(FEEDBACK_CHOICES), horizontal=True,
                              key=f"fb_{index}", label_visibility="collapsed")  # fmt: skip
            comment = st.text_input("Comment (optional)", key=f"fbc_{index}", max_chars=300)
            answers.append((finding, choice, comment))
        if not advice:
            st.write("There are no cost or sizing suggestions to rate.")
        if st.form_submit_button("Finish review"):
            items = [
                FeedbackItem(
                    finding_key=f.feedback_key,
                    category=f.category.value,
                    action=FEEDBACK_CHOICES[choice],
                    comment=comment,
                )  # fmt: skip
                for f, choice, comment in answers
                if FEEDBACK_CHOICES[choice] is not None
            ]
            session.finish(report.review_id, items)
            st.session_state["finished"] = True
            st.rerun()


# ----------------------------------------------------------------------- main


def run_review_clicked(session: ReviewSession, terraform: str, project_id: str) -> None:
    try:
        with st.spinner("Reviewing…"):
            report = session.start(terraform, project_id)
    except TerraformInputError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # show a clear message, never a stack trace
        st.error(f"The review failed unexpectedly ({type(exc).__name__}). Please try again.")
        return
    st.session_state["report"] = report
    st.session_state["review_session"] = session
    st.session_state["finished"] = not session.is_waiting(report.review_id)


def main() -> None:
    st.set_page_config(page_title="GCP Infra Review", page_icon="🛡️", layout="wide")
    st.title("GCP Infra Review Agent")
    st.caption(
        "Reviews Terraform for Google Cloud before you apply it: security, monthly cost and "
        "cheaper alternatives. Read-only: it never touches your GCP project."
    )
    project_id = st.sidebar.text_input("Project", "default", max_chars=64, key="project").strip()
    project_id = project_id or "default"
    settings = developer_settings()
    session = get_session(settings.model_dump_json())
    project_memory(session, project_id)
    if session.deps.llm is None:
        st.info(
            "No LLM API key is configured, so only the rule-based security findings and the "
            "cost estimate are available. Add OPENROUTER_API_KEY to .env for recommendations."
        )

    terraform = terraform_input()
    if st.button("Review", type="primary", key="review"):
        run_review_clicked(session, terraform, project_id)

    report: ReviewReport | None = st.session_state.get("report")
    if report is None:
        return
    show_report(report)
    if st.session_state.get("finished"):
        if report.status == "ok":
            st.success("Review finished and saved to this project's history.")
    else:
        feedback_form(st.session_state["review_session"], report)


main()
