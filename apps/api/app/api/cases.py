from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import RecoveryCase
from app.db.session import get_session
from app.domain.enums import ExperimentGroup, RecoveryCaseStatus, SourceType
from app.domain.recovery_case import RecoveryCaseValidationError
from app.repositories.recovery_cases import RecoveryCaseRepository

router = APIRouter(prefix="/api/cases", tags=["recovery cases"])


class RecoveryCaseCreate(BaseModel):
    merchant_id: UUID
    customer_id: UUID | None = None
    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=255)
    amount_at_risk: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    recovery_window_start: datetime
    recovery_window_end: datetime
    experiment_id: UUID | None = None
    experiment_group: ExperimentGroup | None = None


class RecoveryCaseStatusUpdate(BaseModel):
    status: RecoveryCaseStatus


class RecoveryCaseResponse(BaseModel):
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
    experiment_id: UUID | None
    experiment_group: ExperimentGroup | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def repository(session: Session = Depends(get_session)) -> RecoveryCaseRepository:
    return RecoveryCaseRepository(session)


@router.post(
    "",
    response_model=RecoveryCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recovery_case(
    payload: RecoveryCaseCreate,
    repo: RecoveryCaseRepository = Depends(repository),
) -> RecoveryCase:
    try:
        return repo.create(
            merchant_id=payload.merchant_id,
            customer_id=payload.customer_id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            amount_at_risk=payload.amount_at_risk,
            currency=payload.currency,
            recovery_window_start=payload.recovery_window_start,
            recovery_window_end=payload.recovery_window_end,
            experiment_id=payload.experiment_id,
            experiment_group=payload.experiment_group,
        )
    except RecoveryCaseValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Recovery case conflicts with existing data or missing references.",
        ) from exc


@router.get("", response_model=list[RecoveryCaseResponse])
def list_recovery_cases(
    merchant_id: UUID | None = None,
    repo: RecoveryCaseRepository = Depends(repository),
) -> list[RecoveryCase]:
    return repo.list(merchant_id=merchant_id)


@router.get("/{case_id}", response_model=RecoveryCaseResponse)
def get_recovery_case(
    case_id: UUID,
    repo: RecoveryCaseRepository = Depends(repository),
) -> RecoveryCase:
    recovery_case = repo.get(case_id)
    if recovery_case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    return recovery_case


@router.patch("/{case_id}/status", response_model=RecoveryCaseResponse)
def update_recovery_case_status(
    case_id: UUID,
    payload: RecoveryCaseStatusUpdate,
    repo: RecoveryCaseRepository = Depends(repository),
) -> RecoveryCase:
    try:
        recovery_case = repo.transition(case_id, payload.status)
    except RecoveryCaseValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if recovery_case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    return recovery_case
