"""Module Rapports & Exports : CSV et PDF sur une période (voir services/reports.py)."""
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.deps import require_module, require_roles
from app.models.user import User, UserRole
from app.services import reports

router = APIRouter(dependencies=[Depends(require_module("reports"))])

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.SECURITY_OFFICER, UserRole.DIRECTION)


def _download(content: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pipelines.csv")
def export_pipelines_csv(
    from_: Optional[date] = Query(default=None, alias="from"),
    to: Optional[date] = Query(default=None),
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    return _download(*reports.pipelines_csv(db, *reports.date_range(from_, to)), "text/csv; charset=utf-8")


@router.get("/audit.csv")
def export_audit_csv(
    from_: Optional[date] = Query(default=None, alias="from"),
    to: Optional[date] = Query(default=None),
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    return _download(*reports.audit_csv(db, *reports.date_range(from_, to)), "text/csv; charset=utf-8")


@router.get("/summary.pdf")
def export_summary_pdf(
    from_: Optional[date] = Query(default=None, alias="from"),
    to: Optional[date] = Query(default=None),
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    return _download(*reports.summary_pdf(db, *reports.date_range(from_, to), requested_by=user), "application/pdf")
