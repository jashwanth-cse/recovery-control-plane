from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RecoveryCase
from app.domain.enums import ExperimentGroup, RecoveryCaseStatus, SourceType
from app.domain.recovery_case import TERMINAL_STATUSES


class RecoveryCaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        merchant_id: UUID,
        customer_id: UUID | None,
        source_type: SourceType,
        source_id: str,
        amount_at_risk: int,
        currency: str,
        recovery_window_start: datetime,
        recovery_window_end: datetime,
        experiment_id: UUID | None = None,
        experiment_group: ExperimentGroup | None = None,
    ) -> RecoveryCase:
        recovery_case = RecoveryCase(
            merchant_id=merchant_id,
            customer_id=customer_id,
            source_type=source_type,
            source_id=source_id.strip(),
            amount_at_risk=amount_at_risk,
            currency=currency,
            status=RecoveryCaseStatus.AT_RISK,
            recovery_window_start=recovery_window_start,
            recovery_window_end=recovery_window_end,
            attempt_count=0,
            contact_count=0,
            experiment_id=experiment_id,
            experiment_group=experiment_group,
        )
        recovery_case.validate()
        self.session.add(recovery_case)
        self.session.commit()
        self.session.refresh(recovery_case)
        return recovery_case

    def get(self, case_id: UUID) -> RecoveryCase | None:
        return self.session.get(RecoveryCase, case_id)

    def list(self, *, merchant_id: UUID | None = None) -> list[RecoveryCase]:
        statement = select(RecoveryCase).order_by(RecoveryCase.created_at.desc())
        if merchant_id is not None:
            statement = statement.where(RecoveryCase.merchant_id == merchant_id)
        return list(self.session.scalars(statement))

    def list_active(
        self,
        *,
        merchant_id: UUID | None = None,
        now: datetime | None = None,
    ) -> list[RecoveryCase]:
        observed_at = now or datetime.now(timezone.utc)
        statement = (
            select(RecoveryCase)
            .where(
                RecoveryCase.status.not_in(tuple(TERMINAL_STATUSES)),
                RecoveryCase.recovery_window_end > observed_at,
            )
            .order_by(RecoveryCase.created_at.desc())
        )
        if merchant_id is not None:
            statement = statement.where(RecoveryCase.merchant_id == merchant_id)
        return list(self.session.scalars(statement))

    def transition(
        self,
        case_id: UUID,
        target_status: RecoveryCaseStatus,
    ) -> RecoveryCase | None:
        recovery_case = self.get(case_id)
        if recovery_case is None:
            return None
        recovery_case.transition_to(target_status)
        self.session.commit()
        self.session.refresh(recovery_case)
        return recovery_case
