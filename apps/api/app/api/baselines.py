from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.baseline.service import (
    BaselineConflictError,
    BaselineNotFoundError,
    RuleBaselineService,
)
from app.db.session import get_session
from app.domain.enums import ExperimentGroup, ExperimentStatus

router = APIRouter(prefix="/api/baselines", tags=["rule baseline"])


class BatchRequest(BaseModel):
    merchant_id: UUID
    name: str = Field(min_length=1, max_length=255)
    control_percentage: int = Field(default=50, ge=0, le=100)


class BatchResponse(BaseModel):
    experiment_id: UUID
    name: str
    control_cases: int
    treatment_cases: int
    actions_created: int


class OutcomeRequest(BaseModel):
    outcome: str = Field(pattern="^(RECOVERED|NOT_RECOVERED)$")
    razorpay_payment_id: str | None = Field(default=None, min_length=1, max_length=255)


class OutcomeResponse(BaseModel):
    id: UUID
    action_id: UUID
    outcome: str
    amount_recovered: int
    razorpay_payment_id: str | None
    recovered_at: datetime | None


class GroupReportResponse(BaseModel):
    group: ExperimentGroup
    assigned_cases: int
    recovered_cases: int
    recovery_rate: Decimal


class BaselineReportResponse(BaseModel):
    experiment_id: UUID
    name: str
    status: ExperimentStatus
    control: GroupReportResponse
    treatment: GroupReportResponse
    recovery_rate_lift: Decimal
    recorded_action_outcomes: int
    action_distribution: dict[str, int]


def _service(session: Session) -> RuleBaselineService:
    return RuleBaselineService(session)


@router.post(
    "/batches",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_baseline_batch(
    payload: BatchRequest,
    session: Session = Depends(get_session),
):
    try:
        result = _service(session).run_batch(
            merchant_id=payload.merchant_id,
            name=payload.name,
            control_percentage=payload.control_percentage,
        )
        session.commit()
        return result
    except BaselineNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BaselineConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/actions/{action_id}/outcomes",
    response_model=OutcomeResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_baseline_outcome(
    action_id: UUID,
    payload: OutcomeRequest,
    session: Session = Depends(get_session),
):
    try:
        outcome = _service(session).record_outcome(
            action_id=action_id,
            outcome=payload.outcome,
            razorpay_payment_id=payload.razorpay_payment_id,
        )
        session.commit()
        return outcome
    except BaselineNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BaselineConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{experiment_id}/report",
    response_model=BaselineReportResponse,
)
def baseline_report(
    experiment_id: UUID,
    session: Session = Depends(get_session),
):
    try:
        return _service(session).report(experiment_id)
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
