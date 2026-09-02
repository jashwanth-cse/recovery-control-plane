from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analytics.revenue_at_risk import RevenueAtRiskAggregator
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Merchant, RecoveryCase, RecoveryDecision
from app.db.session import get_session
from app.domain.enums import ActionType, RecoveryCaseStatus, SourceType
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
    merchant,
    *,
    source_id: str,
    amount: int,
    currency: str = "INR",
    status: RecoveryCaseStatus = RecoveryCaseStatus.AT_RISK,
    now: datetime,
    end_offset: timedelta = timedelta(days=10),
) -> RecoveryCase:
    recovery_case = RecoveryCase(
        merchant_id=merchant.id,
        source_type=SourceType.PAYMENT,
        source_id=source_id,
        amount_at_risk=amount,
        currency=currency,
        status=status,
        recovery_window_start=now - timedelta(days=4),
        recovery_window_end=now + end_offset,
        attempt_count=0,
        contact_count=0,
    )
    session.add(recovery_case)
    session.flush()
    return recovery_case


def add_decision(
    session,
    recovery_case: RecoveryCase,
    *,
    probability: str,
    created_at: datetime,
) -> None:
    session.add(
        RecoveryDecision(
            recovery_case_id=recovery_case.id,
            model_version="phase5-test",
            candidate_actions={"actions": ["DELAY"]},
            action_scores={"recovery_probability": probability},
            expected_values={},
            selected_action=ActionType.DELAY,
            selected_action_score=Decimal(probability),
            reason_code="TEST_ESTIMATE",
            explanation="Test estimate.",
            created_at=created_at,
        )
    )


def test_aggregator_groups_currencies_uses_latest_scores_and_ranks_cases():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        merchant = Merchant(name="Dashboard Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        scored = add_case(
            session,
            merchant,
            source_id="pay_scored",
            amount=10000,
            now=now,
        )
        unscored = add_case(
            session,
            merchant,
            source_id="pay_unscored",
            amount=20000,
            now=now,
            end_offset=timedelta(days=1),
        )
        add_case(
            session,
            merchant,
            source_id="pay_usd",
            amount=3000,
            currency="USD",
            now=now,
        )
        add_case(
            session,
            merchant,
            source_id="pay_stopped",
            amount=99999,
            status=RecoveryCaseStatus.STOPPED,
            now=now,
        )
        add_decision(
            session,
            scored,
            probability="0.250000",
            created_at=now - timedelta(hours=1),
        )
        add_decision(
            session,
            scored,
            probability="0.600000",
            created_at=now,
        )
        session.flush()

        snapshot = RevenueAtRiskAggregator(session).build_snapshot(now=now)

        assert snapshot.currencies == [
            snapshot.currencies[0].__class__(
                currency="INR",
                revenue_at_risk=30000,
                expected_recoverable=6000,
                active_cases=2,
                estimated_cases=1,
            ),
            snapshot.currencies[1].__class__(
                currency="USD",
                revenue_at_risk=3000,
                expected_recoverable=0,
                active_cases=1,
                estimated_cases=0,
            ),
        ]
        ranked_ids = [item.case_id for item in snapshot.top_opportunities]
        assert ranked_ids[0] == unscored.id
        scored_opportunity = next(
            item for item in snapshot.top_opportunities if item.case_id == scored.id
        )
        assert scored_opportunity.recovery_probability == Decimal("0.600000")
        assert scored_opportunity.expected_recoverable == 6000


def test_dashboard_api_returns_computed_active_metrics_and_expires_overdue_case():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        merchant = Merchant(name="API Dashboard Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        add_case(
            session,
            merchant,
            source_id="pay_active",
            amount=12500,
            now=now,
        )
        overdue = add_case(
            session,
            merchant,
            source_id="pay_overdue",
            amount=5000,
            now=now,
            end_offset=timedelta(days=-1),
        )
        session.commit()
        overdue_id = overdue.id

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    with TestClient(app) as client:
        response = client.get("/api/dashboard/summary", params={"top_limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["currencies"] == [
        {
            "currency": "INR",
            "revenue_at_risk": 12500,
            "expected_recoverable": 0,
            "active_cases": 1,
            "estimated_cases": 0,
        }
    ]
    assert payload["top_opportunities"][0]["source_id"] == "pay_active"
    assert payload["top_opportunities"][0]["expected_recoverable"] is None
    with factory() as session:
        assert session.get(RecoveryCase, overdue_id).status is RecoveryCaseStatus.EXPIRED
