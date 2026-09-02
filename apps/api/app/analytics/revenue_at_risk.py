from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RecoveryCase, RecoveryDecision
from app.domain.enums import RecoveryCaseStatus, SourceType
from app.repositories.recovery_cases import RecoveryCaseRepository


@dataclass(frozen=True)
class CurrencySummary:
    currency: str
    revenue_at_risk: int
    expected_recoverable: int
    active_cases: int
    estimated_cases: int


@dataclass(frozen=True)
class RankedOpportunity:
    case_id: UUID
    source_type: SourceType
    source_id: str
    status: RecoveryCaseStatus
    amount_at_risk: int
    currency: str
    recovery_probability: Decimal | None
    expected_recoverable: int | None
    priority_score: int
    recovery_window_end: datetime


@dataclass(frozen=True)
class RevenueAtRiskSnapshot:
    generated_at: datetime
    currencies: list[CurrencySummary]
    top_opportunities: list[RankedOpportunity]


class RevenueAtRiskAggregator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build_snapshot(
        self,
        *,
        merchant_id: UUID | None = None,
        top_limit: int = 10,
        now: datetime | None = None,
    ) -> RevenueAtRiskSnapshot:
        observed_at = now or datetime.now(timezone.utc)
        cases = RecoveryCaseRepository(self.session).list_active(
            merchant_id=merchant_id,
            now=observed_at,
        )
        decisions = self._latest_decisions(cases)

        totals: dict[str, dict[str, int]] = {}
        opportunities: list[RankedOpportunity] = []
        for recovery_case in cases:
            probability = self._probability(decisions.get(recovery_case.id))
            expected = self._expected_amount(
                recovery_case.amount_at_risk, probability
            )
            currency_totals = totals.setdefault(
                recovery_case.currency,
                {
                    "revenue_at_risk": 0,
                    "expected_recoverable": 0,
                    "active_cases": 0,
                    "estimated_cases": 0,
                },
            )
            currency_totals["revenue_at_risk"] += recovery_case.amount_at_risk
            currency_totals["active_cases"] += 1
            if expected is not None:
                currency_totals["expected_recoverable"] += expected
                currency_totals["estimated_cases"] += 1

            opportunities.append(
                RankedOpportunity(
                    case_id=recovery_case.id,
                    source_type=recovery_case.source_type,
                    source_id=recovery_case.source_id,
                    status=recovery_case.status,
                    amount_at_risk=recovery_case.amount_at_risk,
                    currency=recovery_case.currency,
                    recovery_probability=probability,
                    expected_recoverable=expected,
                    priority_score=self._priority_score(
                        recovery_case, expected, observed_at
                    ),
                    recovery_window_end=recovery_case.recovery_window_end,
                )
            )

        currencies = [
            CurrencySummary(currency=currency, **values)
            for currency, values in sorted(totals.items())
        ]
        opportunities.sort(
            key=lambda item: (
                item.priority_score,
                item.amount_at_risk,
                str(item.case_id),
            ),
            reverse=True,
        )
        return RevenueAtRiskSnapshot(
            generated_at=observed_at,
            currencies=currencies,
            top_opportunities=opportunities[:top_limit],
        )

    def _latest_decisions(
        self, cases: list[RecoveryCase]
    ) -> dict[UUID, RecoveryDecision]:
        case_ids = [recovery_case.id for recovery_case in cases]
        if not case_ids:
            return {}
        statement = (
            select(RecoveryDecision)
            .where(RecoveryDecision.recovery_case_id.in_(case_ids))
            .order_by(
                RecoveryDecision.created_at.desc(),
                RecoveryDecision.id.desc(),
            )
        )
        latest: dict[UUID, RecoveryDecision] = {}
        for decision in self.session.scalars(statement):
            latest.setdefault(decision.recovery_case_id, decision)
        return latest

    @staticmethod
    def _probability(decision: RecoveryDecision | None) -> Decimal | None:
        if decision is None:
            return None
        raw_probability = decision.action_scores.get("recovery_probability")
        if raw_probability is None:
            return None
        try:
            probability = Decimal(str(raw_probability))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not probability.is_finite():
            return None
        if probability < 0 or probability > 1:
            return None
        return probability

    @staticmethod
    def _expected_amount(amount: int, probability: Decimal | None) -> int | None:
        if probability is None:
            return None
        return int(
            (Decimal(amount) * probability).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

    @staticmethod
    def _priority_score(
        recovery_case: RecoveryCase,
        expected_amount: int | None,
        observed_at: datetime,
    ) -> int:
        window_start = RevenueAtRiskAggregator._as_utc(
            recovery_case.recovery_window_start
        )
        window_end = RevenueAtRiskAggregator._as_utc(
            recovery_case.recovery_window_end
        )
        observed_at = RevenueAtRiskAggregator._as_utc(observed_at)
        total_seconds = (window_end - window_start).total_seconds()
        remaining_seconds = (window_end - observed_at).total_seconds()
        elapsed_fraction = Decimal("0")
        if total_seconds > 0:
            elapsed_fraction = Decimal(
                str(1 - max(0, min(remaining_seconds / total_seconds, 1)))
            )
        urgency_factor = Decimal("1") + elapsed_fraction
        basis = (
            expected_amount
            if expected_amount is not None
            else recovery_case.amount_at_risk
        )
        return int(
            (Decimal(basis) * urgency_factor).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
