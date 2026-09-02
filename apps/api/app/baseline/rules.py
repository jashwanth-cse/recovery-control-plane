from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Payment, RecoveryCase
from app.domain.enums import ActionType, SourceType

TRANSIENT_PAYMENT_SOURCES = frozenset({"bank", "gateway"})
TRANSIENT_PAYMENT_REASONS = frozenset(
    {"bank_error", "payment_failed", "payment_timed_out"}
)


@dataclass(frozen=True)
class RuleSelection:
    action: ActionType
    reason_code: str
    explanation: str


class RecoveryRuleBaseline:
    version = "rule-baseline-v1"

    def select(self, session: Session, recovery_case: RecoveryCase) -> RuleSelection:
        if recovery_case.source_type is SourceType.ORDER:
            return RuleSelection(
                action=ActionType.RECOVERY_LINK,
                reason_code="UNPAID_ORDER",
                explanation="Offer a recovery link for an unpaid order.",
            )
        if recovery_case.source_type is SourceType.PAYMENT_LINK:
            return RuleSelection(
                action=ActionType.DELAY,
                reason_code="EXISTING_PAYMENT_LINK",
                explanation="Wait while the existing payment link remains recoverable.",
            )

        payment = session.scalar(
            select(Payment).where(
                Payment.merchant_id == recovery_case.merchant_id,
                Payment.razorpay_payment_id == recovery_case.source_id,
            )
        )
        if payment is not None and (
            payment.error_source in TRANSIENT_PAYMENT_SOURCES
            or payment.error_reason in TRANSIENT_PAYMENT_REASONS
        ):
            return RuleSelection(
                action=ActionType.RECOVERY_LINK,
                reason_code="TRANSIENT_PAYMENT_FAILURE",
                explanation="Offer a recovery link after a transient payment failure.",
            )
        return RuleSelection(
            action=ActionType.STOP,
            reason_code="NON_TRANSIENT_OR_UNKNOWN_FAILURE",
            explanation="Stop automated recovery for a non-transient or unknown failure.",
        )
