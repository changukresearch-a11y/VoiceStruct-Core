"""CareBase 구조화 API (DB명세 6.4~6.9)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.structure_schema import (
    StructureConfirmRequest,
    StructureRunRequest,
    StructureUpdateRequest,
)
from app.services import confirmation_service, structure_service

router = APIRouter(prefix="/api/structure", tags=["structure"])


@router.post("/run", status_code=201)
def run_structure(req: StructureRunRequest, db: Session = Depends(get_db)):
    result = structure_service.run(db, req.transcript_id, req.domain)
    return JSONResponse(status_code=201, content=result)


@router.get("/{structured_id}")
def get_structure(structured_id: str, db: Session = Depends(get_db)):
    return structure_service.get_detail(db, structured_id)


@router.patch("/{structured_id}")
def update_structure(
    structured_id: str,
    req: StructureUpdateRequest,
    db: Session = Depends(get_db),
):
    return structure_service.update(db, structured_id, req.changed_by, req.edited_fields)


@router.post("/{structured_id}/confirm")
def confirm_structure(
    structured_id: str,
    req: StructureConfirmRequest,
    db: Session = Depends(get_db),
):
    return confirmation_service.confirm(db, structured_id, req.confirmed_by)


@router.get("/{structured_id}/evidence")
def get_evidence(structured_id: str, db: Session = Depends(get_db)):
    return structure_service.list_evidence(db, structured_id)


@router.get("/{structured_id}/changes")
def get_changes(structured_id: str, db: Session = Depends(get_db)):
    return structure_service.list_changes(db, structured_id)
