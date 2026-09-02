from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analytics.revenue_at_risk import RevenueAtRiskAggregator
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.domain.enums import RecoveryCaseStatus, SourceType
from app.recovery.engine import RecoveryCaseEngine

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class CurrencySummaryResponse(BaseModel):
    currency: str
    revenue_at_risk: int
    expected_recoverable: int
    active_cases: int
    estimated_cases: int


class OpportunityResponse(BaseModel):
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


class DashboardSummaryResponse(BaseModel):
    generated_at: datetime
    currencies: list[CurrencySummaryResponse]
    top_opportunities: list[OpportunityResponse]


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    merchant_id: UUID | None = None,
    top_limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    RecoveryCaseEngine(
        session, recovery_window_days=settings.recovery_window_days
    ).expire_due_cases(merchant_id=merchant_id)
    snapshot = RevenueAtRiskAggregator(session).build_snapshot(
        merchant_id=merchant_id,
        top_limit=top_limit,
    )
    session.commit()
    return snapshot
