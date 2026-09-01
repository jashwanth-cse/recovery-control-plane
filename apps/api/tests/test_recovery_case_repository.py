from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Customer, Merchant
from app.domain.enums import (
    CustomerConsentStatus,
    RecoveryCaseStatus,
    SourceType,
)
from app.domain.recovery_case import (
    InvalidRecoveryCaseTransition,
    RecoveryCaseValidationError,
)
from app.repositories.recovery_cases import RecoveryCaseRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as active_session:
        yield active_session


@pytest.fixture()
def merchant_and_customer(session):
    merchant = Merchant(name="Test Merchant", status="ACTIVE")
    session.add(merchant)
    session.commit()
    session.refresh(merchant)

    customer = Customer(
        merchant_id=merchant.id,
        external_customer_id="cust_test",
        email="customer@example.com",
        phone="+910000000000",
        consent_status=CustomerConsentStatus.OPTED_IN,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return merchant, customer


def create_case(repo, merchant, customer):
    now = datetime.now(timezone.utc)
    return repo.create(
        merchant_id=merchant.id,
        customer_id=customer.id,
        source_type=SourceType.PAYMENT,
        source_id="pay_failed_test",
        amount_at_risk=250000,
        currency="INR",
        recovery_window_start=now,
        recovery_window_end=now + timedelta(days=14),
    )


def test_repository_can_create_get_and_list_recovery_case(
    session,
    merchant_and_customer,
):
    merchant, customer = merchant_and_customer
    repo = RecoveryCaseRepository(session)

    recovery_case = create_case(repo, merchant, customer)

    fetched_case = repo.get(recovery_case.id)
    listed_cases = repo.list(merchant_id=merchant.id)

    assert fetched_case is not None
    assert fetched_case.id == recovery_case.id
    assert fetched_case.status == RecoveryCaseStatus.AT_RISK
    assert listed_cases == [recovery_case]


def test_repository_can_update_recovery_case_status(
    session,
    merchant_and_customer,
):
    merchant, customer = merchant_and_customer
    repo = RecoveryCaseRepository(session)
    recovery_case = create_case(repo, merchant, customer)

    updated_case = repo.transition(
        recovery_case.id,
        RecoveryCaseStatus.ELIGIBILITY_CHECK,
    )

    assert updated_case is not None
    assert updated_case.status == RecoveryCaseStatus.ELIGIBILITY_CHECK
    assert repo.get(recovery_case.id).status == RecoveryCaseStatus.ELIGIBILITY_CHECK


def test_repository_rejects_invalid_state_transition(
    session,
    merchant_and_customer,
):
    merchant, customer = merchant_and_customer
    repo = RecoveryCaseRepository(session)
    recovery_case = create_case(repo, merchant, customer)

    with pytest.raises(InvalidRecoveryCaseTransition):
        repo.transition(recovery_case.id, RecoveryCaseStatus.ACTION_PENDING)


def test_repository_rejects_invalid_case_values(session, merchant_and_customer):
    merchant, customer = merchant_and_customer
    repo = RecoveryCaseRepository(session)
    now = datetime.now(timezone.utc)

    with pytest.raises(RecoveryCaseValidationError):
        repo.create(
            merchant_id=merchant.id,
            customer_id=customer.id,
            source_type=SourceType.PAYMENT,
            source_id="pay_failed_bad_amount",
            amount_at_risk=0,
            currency="INR",
            recovery_window_start=now,
            recovery_window_end=now + timedelta(days=14),
        )
