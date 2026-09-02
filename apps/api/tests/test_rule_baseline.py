from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.baseline.rules import RecoveryRuleBaseline
from app.baseline.service import BaselineConflictError, RuleBaselineService
from app.analytics.revenue_at_risk import RevenueAtRiskAggregator
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    ActionOutcome,
    ExperimentAssignment,
    Merchant,
    Payment,
    RecoveryAction,
    RecoveryCase,
    RecoveryDecision,
)
from app.db.session import get_session
from app.domain.enums import (
    ActionType,
    ExperimentGroup,
    RecoveryCaseStatus,
    SourceType,
)
from app.main import create_app


def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def add_case(
    session,
    merchant: Merchant,
    source_id: str,
    *,
    source_type: SourceType = SourceType.ORDER,
) -> RecoveryCase:
    now = datetime.now(timezone.utc)
    recovery_case = RecoveryCase(
        merchant_id=merchant.id,
        source_type=source_type,
        source_id=source_id,
        amount_at_risk=10000,
        currency="INR",
        status=RecoveryCaseStatus.AT_RISK,
        recovery_window_start=now,
        recovery_window_end=now + timedelta(days=14),
        attempt_count=0,
        contact_count=0,
    )
    session.add(recovery_case)
    session.flush()
    return recovery_case


def test_rules_select_recovery_link_delay_and_stop_without_execution():
    factory = session_factory()
    with factory() as session:
        merchant = Merchant(name="Rule Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        payment_case = add_case(
            session,
            merchant,
            "pay_transient",
            source_type=SourceType.PAYMENT,
        )
        session.add(
            Payment(
                merchant_id=merchant.id,
                razorpay_payment_id="pay_transient",
                amount=10000,
                currency="INR",
                status="failed",
                error_source="bank",
            )
        )
        order_case = add_case(session, merchant, "order_rule")
        link_case = add_case(
            session,
            merchant,
            "plink_rule",
            source_type=SourceType.PAYMENT_LINK,
        )
        unknown_case = add_case(
            session,
            merchant,
            "pay_unknown",
            source_type=SourceType.PAYMENT,
        )
        rules = RecoveryRuleBaseline()

        assert rules.select(session, payment_case).action is ActionType.RECOVERY_LINK
        assert rules.select(session, order_case).action is ActionType.RECOVERY_LINK
        assert rules.select(session, link_case).action is ActionType.DELAY
        assert rules.select(session, unknown_case).action is ActionType.STOP


def test_batch_assigns_exact_control_share_and_only_treatment_gets_actions():
    factory = session_factory()
    with factory() as session:
        merchant = Merchant(name="Batch Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        cases = [add_case(session, merchant, f"order_batch_{index}") for index in range(4)]

        result = RuleBaselineService(session).run_batch(
            merchant_id=merchant.id,
            name="Rules vs no intervention",
            control_percentage=50,
        )
        session.commit()

        assert result.control_cases == 2
        assert result.treatment_cases == 2
        assert result.actions_created == 2
        assignments = list(session.scalars(select(ExperimentAssignment)))
        assert sum(a.group_name is ExperimentGroup.CONTROL for a in assignments) == 2
        assert sum(a.group_name is ExperimentGroup.TREATMENT for a in assignments) == 2
        assert session.scalar(select(func.count()).select_from(RecoveryDecision)) == 2
        assert session.scalar(select(func.count()).select_from(RecoveryAction)) == 2
        dashboard = RevenueAtRiskAggregator(session).build_snapshot()
        assert dashboard.currencies[0].expected_recoverable == 0
        assert dashboard.currencies[0].estimated_cases == 0
        for recovery_case in cases:
            if recovery_case.experiment_group is ExperimentGroup.TREATMENT:
                assert recovery_case.status is RecoveryCaseStatus.DECISION_READY
            else:
                assert recovery_case.status is RecoveryCaseStatus.AT_RISK

        with pytest.raises(BaselineConflictError):
            RuleBaselineService(session).run_batch(
                merchant_id=merchant.id,
                name="Duplicate batch",
                control_percentage=50,
            )


def test_outcomes_require_captured_evidence_are_idempotent_and_feed_report():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        merchant = Merchant(name="Outcome Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        for index in range(4):
            add_case(session, merchant, f"order_outcome_{index}")
        service = RuleBaselineService(session)
        batch = service.run_batch(
            merchant_id=merchant.id,
            name="Outcome comparison",
            control_percentage=50,
            now=now,
        )
        action = session.scalar(select(RecoveryAction))

        with pytest.raises(BaselineConflictError):
            service.record_outcome(
                action_id=action.id,
                outcome="RECOVERED",
                razorpay_payment_id="pay_missing",
                now=now,
            )

        session.add(
            Payment(
                merchant_id=merchant.id,
                razorpay_payment_id="pay_captured_baseline",
                amount=8000,
                currency="INR",
                status="captured",
            )
        )
        session.flush()
        first = service.record_outcome(
            action_id=action.id,
            outcome="RECOVERED",
            razorpay_payment_id="pay_captured_baseline",
            now=now,
        )
        second = service.record_outcome(
            action_id=action.id,
            outcome="RECOVERED",
            razorpay_payment_id="pay_captured_baseline",
            now=now,
        )
        session.commit()

        report = service.report(batch.experiment_id)
        assert first.id == second.id
        assert first.amount_recovered == 8000
        assert report.control.assigned_cases == 2
        assert report.control.recovery_rate == 0
        assert report.treatment.assigned_cases == 2
        assert report.treatment.recovered_cases == 1
        assert report.treatment.recovery_rate == pytest.approx(0.5)
        assert report.recovery_rate_lift == pytest.approx(0.5)
        assert report.recorded_action_outcomes == 1
        assert report.action_distribution == {"RECOVERY_LINK": 2}
        assert session.scalar(select(func.count()).select_from(ActionOutcome)) == 1


def test_baseline_api_runs_batch_and_returns_comparison_report():
    factory = session_factory()
    with factory() as session:
        merchant = Merchant(name="Baseline API Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        add_case(session, merchant, "order_api_1")
        add_case(session, merchant, "order_api_2")
        session.commit()
        merchant_id = merchant.id

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = get_settings
    with TestClient(app) as client:
        batch_response = client.post(
            "/api/baselines/batches",
            json={
                "merchant_id": str(merchant_id),
                "name": "API comparison",
                "control_percentage": 50,
            },
        )
        assert batch_response.status_code == 201
        batch = batch_response.json()
        report_response = client.get(
            f"/api/baselines/{batch['experiment_id']}/report"
        )

    assert batch["control_cases"] == 1
    assert batch["treatment_cases"] == 1
    assert batch["actions_created"] == 1
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["control"]["group"] == "CONTROL"
    assert report["treatment"]["group"] == "TREATMENT"
    assert report["action_distribution"] == {"RECOVERY_LINK": 1}
