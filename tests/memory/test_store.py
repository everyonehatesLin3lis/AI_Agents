from memory.feedback_policy import apply_feedback
from memory.store import FeedbackAction, FeedbackItem, MemoryStore, ProjectConstraints
from tools.models import Category, Finding, Severity


def _finding(category: Category, severity: Severity, rule_id: str | None = None) -> Finding:
    return Finding(
        severity=severity,
        resource="google_sql_database_instance.main",
        issue="issue",
        recommendation="do something",
        rule_id=rule_id,
        category=category,
    )


def test_constraints_round_trip_and_default_to_empty(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite")
    assert store.get_constraints("shop") == ProjectConstraints()

    saved = ProjectConstraints(budget_monthly_usd=300, region="europe-west1", preferences=["x"])
    store.save_constraints("shop", saved)
    store.save_constraints("shop", saved.model_copy(update={"budget_monthly_usd": 500}))

    assert store.get_constraints("shop").budget_monthly_usd == 500
    assert store.get_constraints("other-project") == ProjectConstraints()


def test_feedback_and_reviews_are_kept_per_project(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite")
    item = FeedbackItem(finding_key="cost:x", category="cost", action=FeedbackAction.DISMISS)

    store.add_feedback("shop", "review-1", [item])
    store.save_review("review-1", "shop", {"summary": "ok"})

    assert store.get_feedback("shop") == [item]
    assert store.get_feedback("blog") == []
    assert store.list_reviews("shop")[0].report == {"summary": "ok"}


def test_memory_survives_a_new_store_object(tmp_path):
    path = tmp_path / "memory.sqlite"
    MemoryStore(path).save_constraints("shop", ProjectConstraints(region="us-east1"))

    assert MemoryStore(path).get_constraints("shop").region == "us-east1"


def test_dismissed_cost_suggestion_is_deprioritized_and_moved_last():
    cost = _finding(Category.COST, Severity.MEDIUM)
    low_security = _finding(Category.SECURITY, Severity.LOW, "SQL-005")
    feedback = [
        FeedbackItem(finding_key=cost.feedback_key, category="cost", action=FeedbackAction.DISMISS)
    ]

    result = apply_feedback([cost, low_security], feedback)

    assert [f.category for f in result] == [Category.SECURITY, Category.COST]
    assert result[1].deprioritized is True
    assert result[1].severity == Severity.MEDIUM  # severity itself never changes


def test_feedback_can_never_touch_a_security_finding():
    critical = _finding(Category.SECURITY, Severity.CRITICAL, "SQL-001")
    feedback = [
        FeedbackItem(finding_key="SQL-001", category="security", action=FeedbackAction.DISMISS),
        FeedbackItem(finding_key="SQL-001", category="cost", action=FeedbackAction.DISMISS),
    ]

    result = apply_feedback([critical], feedback)

    assert result == [critical]
    assert result[0].deprioritized is False


def test_a_later_helpful_cancels_an_earlier_dismiss():
    cost = _finding(Category.COST, Severity.LOW)
    key = cost.feedback_key
    feedback = [
        FeedbackItem(finding_key=key, category="cost", action=FeedbackAction.DISMISS),
        FeedbackItem(finding_key=key, category="cost", action=FeedbackAction.HELPFUL),
    ]

    assert apply_feedback([cost], feedback)[0].deprioritized is False
