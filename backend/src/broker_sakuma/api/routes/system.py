from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, require_api_key
from broker_sakuma.api.schemas import KillSwitchRequest, SystemActionResponse
from broker_sakuma.services.system_control_service import SystemControlService, SystemTransitionError

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_api_key)])


@router.post("/start", response_model=SystemActionResponse)
def start_system(db: Session = Depends(get_db)) -> SystemActionResponse:
    try:
        state = SystemControlService(db).start(actor="local_api")
    except SystemTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SystemActionResponse(system_state=state.value)


@router.post("/pause", response_model=SystemActionResponse)
def pause_system(db: Session = Depends(get_db)) -> SystemActionResponse:
    try:
        state = SystemControlService(db).pause(actor="local_api")
    except SystemTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SystemActionResponse(system_state=state.value)


@router.post("/resume", response_model=SystemActionResponse)
def resume_system(db: Session = Depends(get_db)) -> SystemActionResponse:
    try:
        state = SystemControlService(db).resume(actor="local_api")
    except SystemTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SystemActionResponse(system_state=state.value)


@router.post("/kill-switch", response_model=SystemActionResponse)
def kill_switch(payload: KillSwitchRequest, db: Session = Depends(get_db)) -> SystemActionResponse:
    """Sensitive operation: requires an explicit, non-empty reason in the
    request body (spec section 38: "Operações sensíveis exigem autorização
    adicional"). Reachable from any state, and idempotent if already
    engaged — pressing it twice is safe, not a duplicate alert.
    """

    if not payload.reason.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="reason is required")

    state = SystemControlService(db).engage_kill_switch(actor="local_api", reason=payload.reason)
    return SystemActionResponse(system_state=state.value)
