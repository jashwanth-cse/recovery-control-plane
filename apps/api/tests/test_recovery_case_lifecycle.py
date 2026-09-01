import pytest

from app.domain.enums import RecoveryCaseStatus
from app.domain.recovery_case import (
    InvalidRecoveryCaseTransition,
    ensure_valid_transition,
)


def test_core_recovery_case_path_allows_expected_transitions():
    path = [
        RecoveryCaseStatus.AT_RISK,
        RecoveryCaseStatus.ELIGIBILITY_CHECK,
        RecoveryCaseStatus.ASSESSING,
        RecoveryCaseStatus.DECISION_READY,
        RecoveryCaseStatus.POLICY_CHECK,
        RecoveryCaseStatus.ACTION_PENDING,
        RecoveryCaseStatus.EXECUTING,
        RecoveryCaseStatus.RECOVERED,
    ]

    for current_status, target_status in zip(path, path[1:]):
        ensure_valid_transition(current_status, target_status)


def test_invalid_transition_is_rejected():
    with pytest.raises(InvalidRecoveryCaseTransition):
        ensure_valid_transition(
            RecoveryCaseStatus.AT_RISK,
            RecoveryCaseStatus.ACTION_PENDING,
        )


def test_terminal_status_rejects_further_transition():
    with pytest.raises(InvalidRecoveryCaseTransition):
        ensure_valid_transition(
            RecoveryCaseStatus.RECOVERED,
            RecoveryCaseStatus.REASSESS,
        )


def test_policy_check_can_escalate_case():
    ensure_valid_transition(
        RecoveryCaseStatus.POLICY_CHECK,
        RecoveryCaseStatus.ESCALATED,
    )
