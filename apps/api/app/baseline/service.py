from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.baseline.rules import RecoveryRuleBaseline
from app.db.models import (
    ActionOutcome,
    AuditEvent,
    Experiment,
    ExperimentAssignment,
    Merchant,
    Payment,
    RecoveryAction,
    RecoveryCase,
    RecoveryDecision,
)
from app.domain.enums import (
    AuditActorType,
    ExperimentGroup,
    ExperimentStatus,
    RecoveryActionStatus,
    RecoveryCaseStatus,
)
from app.domain.recovery_case import TERMINAL_STATUSES
from app.repositories.recovery_cases import RecoveryCaseRepository

ELIGIBLE_BASELINE_STATUSES = frozenset(
    {
        RecoveryCaseStatus.AT_RISK,
        RecoveryCaseStatus.ELIGIBILITY_CHECK,
        RecoveryCaseStatus.ASSESSING,
    }
)
RECOVERED_OUTCOME = "RECOVERED"
NOT_RECOVERED_OUTCOME = "NOT_RECOVERED"


class BaselineError(RuntimeError):
    pass


class BaselineNotFoundError(BaselineError):
    pass


class BaselineConflictError(BaselineError):
    pass


@dataclass(frozen=True)
class BatchResult:
    experiment_id: UUID
    name: str
    control_cases: int
    treatment_cases: int
    actions_created: int


@dataclass(frozen=True)
class GroupReport:
    group: ExperimentGroup
    assigned_cases: int
    recovered_cases: int
    recovery_rate: Decimal


@dataclass(frozen=True)
class BaselineReport:
    experiment_id: UUID
    name: str
    status: ExperimentStatus
    control: GroupReport
    treatment: GroupReport
    recovery_rate_lift: Decimal
    recorded_action_outcomes: int
    action_distribution: dict[str, int]


class RuleBaselineService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.rules = RecoveryRuleBaseline()

    def run_batch(
        self,
        *,
        merchant_id: UUID,
        name: str,
        control_percentage: int,
        now: datetime | None = None,
    ) -> BatchResult:
        observed_at = now or datetime.now(timezone.utc)
        merchant = self.session.get(Merchant, merchant_id)
        if merchant is None:
            raise BaselineNotFoundError("Merchant not found.")
        if merchant.status != "ACTIVE":
            raise BaselineConflictError("Merchant is not active.")
        normalized_name = name.strip()
        if not normalized_name:
            raise BaselineConflictError("Baseline name is required.")

        eligible_cases = [
            recovery_case
            for recovery_case in RecoveryCaseRepository(self.session).list_active(
                merchant_id=merchant_id,
                now=observed_at,
            )
            if recovery_case.experiment_id is None
            and recovery_case.status in ELIGIBLE_BASELINE_STATUSES
        ]
        if not eligible_cases:
            raise BaselineConflictError("No unassigned active cases are eligible.")

        experiment = Experiment(
            merchant_id=merchant_id,
            name=normalized_name,
            control_percentage=control_percentage,
            status=ExperimentStatus.RUNNING,
        )
        self.session.add(experiment)
        self.session.flush()

        ranked_cases = sorted(
            eligible_cases,
            key=lambda item: sha256(
                f"{experiment.id}:{item.id}".encode("ascii")
            ).digest(),
        )
        control_count = self._control_count(
            len(ranked_cases), control_percentage
        )
        actions_created = 0
        for index, recovery_case in enumerate(ranked_cases):
            group = (
                ExperimentGroup.CONTROL
                if index < control_count
                else ExperimentGroup.TREATMENT
            )
            assignment = ExperimentAssignment(
                experiment_id=experiment.id,
                recovery_case_id=recovery_case.id,
                group_name=group,
                assigned_at=observed_at,
            )
            self.session.add(assignment)
            recovery_case.experiment_id = experiment.id
            recovery_case.experiment_group = group
            self._audit_assignment(recovery_case, experiment, group)
            if group is ExperimentGroup.TREATMENT:
                self._create_rule_decision(recovery_case, observed_at)
                actions_created += 1

        self.session.flush()
        return BatchResult(
            experiment_id=experiment.id,
            name=experiment.name,
            control_cases=control_count,
            treatment_cases=len(ranked_cases) - control_count,
            actions_created=actions_created,
        )

    def record_outcome(
        self,
        *,
        action_id: UUID,
        outcome: str,
        razorpay_payment_id: str | None = None,
        now: datetime | None = None,
    ) -> ActionOutcome:
        observed_at = now or datetime.now(timezone.utc)
        action = self.session.get(RecoveryAction, action_id)
        if action is None:
            raise BaselineNotFoundError("Recovery action not found.")
        existing = self.session.scalar(
            select(ActionOutcome).where(ActionOutcome.action_id == action_id)
        )
        if existing is not None:
            if existing.outcome != outcome:
                raise BaselineConflictError(
                    "A different outcome is already recorded for this action."
                )
            return existing

        recovery_case = self.session.get(RecoveryCase, action.recovery_case_id)
        if recovery_case is None:
            raise BaselineNotFoundError("Recovery case not found.")
        assignment = self.session.scalar(
            select(ExperimentAssignment).where(
                ExperimentAssignment.experiment_id == recovery_case.experiment_id,
                ExperimentAssignment.recovery_case_id == recovery_case.id,
                ExperimentAssignment.group_name == ExperimentGroup.TREATMENT,
            )
        )
        baseline_version = (action.policy_result or {}).get("baseline_version")
        if assignment is None or baseline_version != self.rules.version:
            raise BaselineConflictError(
                "Outcome does not belong to a rule-baseline treatment action."
            )

        amount_recovered = 0
        recovered_at = None
        if outcome == RECOVERED_OUTCOME:
            if recovery_case.status in TERMINAL_STATUSES and (
                recovery_case.status is not RecoveryCaseStatus.RECOVERED
            ):
                raise BaselineConflictError("A stopped case cannot be recovered.")
            payment = self.session.scalar(
                select(Payment).where(
                    Payment.merchant_id == recovery_case.merchant_id,
                    Payment.razorpay_payment_id == razorpay_payment_id,
                    Payment.status == "captured",
                )
            )
            if payment is None:
                raise BaselineConflictError(
                    "Recovered outcomes require a reconciled captured payment."
                )
            amount_recovered = payment.amount
            recovered_at = observed_at
            if recovery_case.status is not RecoveryCaseStatus.RECOVERED:
                recovery_case.transition_to(RecoveryCaseStatus.RECOVERED)
        elif outcome != NOT_RECOVERED_OUTCOME:
            raise BaselineConflictError("Outcome is not supported.")
        elif razorpay_payment_id is not None:
            raise BaselineConflictError(
                "A non-recovered outcome cannot reference a captured payment."
            )

        recorded = ActionOutcome(
            action_id=action.id,
            outcome=outcome,
            amount_recovered=amount_recovered,
            razorpay_payment_id=razorpay_payment_id,
            recovered_at=recovered_at,
        )
        self.session.add(recorded)
        self.session.add(
            AuditEvent(
                recovery_case_id=recovery_case.id,
                event_type="BASELINE_OUTCOME_RECORDED",
                actor_type=AuditActorType.SYSTEM,
                action_snapshot={
                    "action_id": str(action.id),
                    "outcome": outcome,
                    "amount_recovered": amount_recovered,
                    "razorpay_payment_id": razorpay_payment_id,
                },
            )
        )
        self.session.flush()
        return recorded

    def report(self, experiment_id: UUID) -> BaselineReport:
        experiment = self.session.get(Experiment, experiment_id)
        if experiment is None:
            raise BaselineNotFoundError("Baseline experiment not found.")
        rows = list(
            self.session.execute(
                select(ExperimentAssignment, RecoveryCase)
                .join(
                    RecoveryCase,
                    RecoveryCase.id == ExperimentAssignment.recovery_case_id,
                )
                .where(ExperimentAssignment.experiment_id == experiment_id)
            )
        )
        groups = {
            group: self._group_report(group, rows)
            for group in (ExperimentGroup.CONTROL, ExperimentGroup.TREATMENT)
        }
        treatment_case_ids = [
            recovery_case.id
            for assignment, recovery_case in rows
            if assignment.group_name is ExperimentGroup.TREATMENT
        ]
        action_distribution: dict[str, int] = {}
        recorded_outcomes = 0
        if treatment_case_ids:
            for action_type, count in self.session.execute(
                select(RecoveryAction.action_type, func.count(RecoveryAction.id))
                .where(RecoveryAction.recovery_case_id.in_(treatment_case_ids))
                .group_by(RecoveryAction.action_type)
            ):
                action_distribution[action_type.value] = count
            recorded_outcomes = self.session.scalar(
                select(func.count(ActionOutcome.id))
                .join(RecoveryAction, RecoveryAction.id == ActionOutcome.action_id)
                .where(RecoveryAction.recovery_case_id.in_(treatment_case_ids))
            ) or 0

        return BaselineReport(
            experiment_id=experiment.id,
            name=experiment.name,
            status=experiment.status,
            control=groups[ExperimentGroup.CONTROL],
            treatment=groups[ExperimentGroup.TREATMENT],
            recovery_rate_lift=(
                groups[ExperimentGroup.TREATMENT].recovery_rate
                - groups[ExperimentGroup.CONTROL].recovery_rate
            ),
            recorded_action_outcomes=recorded_outcomes,
            action_distribution=action_distribution,
        )

    def _create_rule_decision(
        self, recovery_case: RecoveryCase, observed_at: datetime
    ) -> None:
        selection = self.rules.select(self.session, recovery_case)
        if recovery_case.status is RecoveryCaseStatus.AT_RISK:
            recovery_case.transition_to(RecoveryCaseStatus.ELIGIBILITY_CHECK)
        if recovery_case.status is RecoveryCaseStatus.ELIGIBILITY_CHECK:
            recovery_case.transition_to(RecoveryCaseStatus.ASSESSING)
        if recovery_case.status is RecoveryCaseStatus.ASSESSING:
            recovery_case.transition_to(RecoveryCaseStatus.DECISION_READY)
        decision = RecoveryDecision(
            recovery_case_id=recovery_case.id,
            model_version=self.rules.version,
            candidate_actions={"actions": [selection.action.value]},
            action_scores={"rule_match": 1},
            expected_values={},
            selected_action=selection.action,
            selected_action_score=Decimal("1"),
            reason_code=selection.reason_code,
            explanation=selection.explanation,
            created_at=observed_at,
        )
        action = RecoveryAction(
            recovery_case_id=recovery_case.id,
            action_type=selection.action,
            status=RecoveryActionStatus.PENDING,
            policy_result={
                "evaluation": "NOT_RUN",
                "baseline_version": self.rules.version,
            },
        )
        self.session.add_all([decision, action])
        self.session.add(
            AuditEvent(
                recovery_case_id=recovery_case.id,
                event_type="RULE_BASELINE_DECISION_RECORDED",
                actor_type=AuditActorType.POLICY,
                decision_snapshot={
                    "version": self.rules.version,
                    "selected_action": selection.action.value,
                    "reason_code": selection.reason_code,
                },
                policy_snapshot={"evaluation": "NOT_RUN"},
            )
        )

    def _audit_assignment(
        self,
        recovery_case: RecoveryCase,
        experiment: Experiment,
        group: ExperimentGroup,
    ) -> None:
        self.session.add(
            AuditEvent(
                recovery_case_id=recovery_case.id,
                event_type="BASELINE_GROUP_ASSIGNED",
                actor_type=AuditActorType.SYSTEM,
                input_snapshot={
                    "experiment_id": str(experiment.id),
                    "group": group.value,
                    "control_percentage": experiment.control_percentage,
                },
            )
        )

    @staticmethod
    def _control_count(total: int, percentage: int) -> int:
        count = (total * percentage + 50) // 100
        if total >= 2 and 0 < percentage < 100:
            return min(max(count, 1), total - 1)
        return count

    @staticmethod
    def _group_report(group, rows) -> GroupReport:
        cases = [
            recovery_case
            for assignment, recovery_case in rows
            if assignment.group_name is group
        ]
        recovered = sum(
            recovery_case.status is RecoveryCaseStatus.RECOVERED
            for recovery_case in cases
        )
        rate = Decimal("0")
        if cases:
            rate = (Decimal(recovered) / Decimal(len(cases))).quantize(
                Decimal("0.000001")
            )
        return GroupReport(
            group=group,
            assigned_cases=len(cases),
            recovered_cases=recovered,
            recovery_rate=rate,
        )
