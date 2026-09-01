from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.domain.enums import RecoveryCaseStatus, SourceType


TERMINAL_STATUSES = frozenset(
    {
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.STOPPED,
        RecoveryCaseStatus.EXPIRED,
        RecoveryCaseStatus.ESCALATED,
    }
)

ALLOWED_TRANSITIONS: dict[RecoveryCaseStatus, frozenset[RecoveryCaseStatus]] = {
    RecoveryCaseStatus.AT_RISK: frozenset({RecoveryCaseStatus.ELIGIBILITY_CHECK}),
    RecoveryCaseStatus.ELIGIBILITY_CHECK: frozenset(
        {RecoveryCaseStatus.ASSESSING, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.ASSESSING: frozenset(
        {RecoveryCaseStatus.DECISION_READY, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.DECISION_READY: frozenset(
        {RecoveryCaseStatus.POLICY_CHECK, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.POLICY_CHECK: frozenset(
        {
            RecoveryCaseStatus.ACTION_PENDING,
            RecoveryCaseStatus.STOPPED,
            RecoveryCaseStatus.ESCALATED,
        }
    ),
    RecoveryCaseStatus.ACTION_PENDING: frozenset(
        {RecoveryCaseStatus.EXECUTING, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.EXECUTING: frozenset(
        {
            RecoveryCaseStatus.RECOVERED,
            RecoveryCaseStatus.ACTION_FAILED,
            RecoveryCaseStatus.STOPPED,
        }
    ),
    RecoveryCaseStatus.ACTION_FAILED: frozenset(
        {RecoveryCaseStatus.REASSESS, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.REASSESS: frozenset(
        {RecoveryCaseStatus.NEXT_ACTION, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.NEXT_ACTION: frozenset(
        {RecoveryCaseStatus.POLICY_CHECK, RecoveryCaseStatus.STOPPED}
    ),
    RecoveryCaseStatus.RECOVERED: frozenset(),
    RecoveryCaseStatus.STOPPED: frozenset(),
    RecoveryCaseStatus.EXPIRED: frozenset(),
    RecoveryCaseStatus.ESCALATED: frozenset(),
}


class RecoveryCaseValidationError(ValueError):
    """Raised when a recovery case violates domain invariants."""


class InvalidRecoveryCaseTransition(RecoveryCaseValidationError):
    def __init__(
        self,
        current_status: RecoveryCaseStatus,
        target_status: RecoveryCaseStatus,
    ) -> None:
        super().__init__(
            f"Invalid recovery case transition: {current_status} -> {target_status}"
        )
        self.current_status = current_status
        self.target_status = target_status


def ensure_valid_transition(
    current_status: RecoveryCaseStatus,
    target_status: RecoveryCaseStatus,
) -> None:
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        raise InvalidRecoveryCaseTransition(current_status, target_status)


def ensure_valid_case_values(
    source_type: SourceType,
    source_id: str,
    amount_at_risk: int,
    currency: str,
    recovery_window_start: datetime,
    recovery_window_end: datetime,
) -> None:
    if not isinstance(source_type, SourceType):
        raise RecoveryCaseValidationError("source_type is not supported")
    if not source_id.strip():
        raise RecoveryCaseValidationError("source_id is required")
    if amount_at_risk <= 0:
        raise RecoveryCaseValidationError("amount_at_risk must be positive")
    if len(currency) != 3 or not currency.isalpha() or currency.upper() != currency:
        raise RecoveryCaseValidationError("currency must be a 3-letter uppercase code")
    if recovery_window_start >= recovery_window_end:
        raise RecoveryCaseValidationError(
            "recovery_window_end must be after recovery_window_start"
        )


@dataclass(frozen=True)
class RecoveryCaseSnapshot:
    id: UUID
    merchant_id: UUID
    customer_id: UUID | None
    source_type: SourceType
    source_id: str
    amount_at_risk: int
    currency: str
    status: RecoveryCaseStatus
    recovery_window_start: datetime
    recovery_window_end: datetime
    attempt_count: int
    contact_count: int

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.recovery_window_end
