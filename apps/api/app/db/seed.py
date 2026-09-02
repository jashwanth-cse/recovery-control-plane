from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import Customer, Merchant, RecoveryCase
from app.db.session import get_sessionmaker
from app.domain.enums import CustomerConsentStatus, SourceType
from app.repositories.recovery_cases import RecoveryCaseRepository


def seed_development_data() -> None:
    session_factory = get_sessionmaker()
    with session_factory() as session:
        merchant = session.scalar(
            select(Merchant).where(Merchant.name == "Demo Razorpay Merchant")
        )
        if merchant is None:
            merchant = Merchant(
                name="Demo Razorpay Merchant",
                status="ACTIVE",
                razorpay_account_id="acc_demo_phase4",
                razorpay_key_id="rzp_test_demo_reference",
                secret_reference="env:RAZORPAY_KEY_SECRET",
            )
            session.add(merchant)
            session.commit()
            session.refresh(merchant)
        elif merchant.razorpay_account_id is None:
            merchant.razorpay_account_id = "acc_demo_phase4"
            session.commit()

        customer = session.scalar(
            select(Customer).where(
                Customer.merchant_id == merchant.id,
                Customer.external_customer_id == "cust_demo_phase1",
            )
        )
        if customer is None:
            customer = Customer(
                merchant_id=merchant.id,
                external_customer_id="cust_demo_phase1",
                email="demo.customer@example.com",
                phone="+910000000000",
                consent_status=CustomerConsentStatus.OPTED_IN,
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)

        existing_case = session.scalar(
            select(RecoveryCase).where(
                RecoveryCase.merchant_id == merchant.id,
                RecoveryCase.source_type == SourceType.PAYMENT,
                RecoveryCase.source_id == "pay_demo_failed_phase1",
            )
        )
        if existing_case is None:
            now = datetime.now(timezone.utc)
            RecoveryCaseRepository(session).create(
                merchant_id=merchant.id,
                customer_id=customer.id,
                source_type=SourceType.PAYMENT,
                source_id="pay_demo_failed_phase1",
                amount_at_risk=499900,
                currency="INR",
                recovery_window_start=now,
                recovery_window_end=now + timedelta(days=14),
            )


if __name__ == "__main__":
    seed_development_data()
