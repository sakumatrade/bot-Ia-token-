from __future__ import annotations

import pytest

from broker_sakuma.core.enums import SystemState
from broker_sakuma.engines.system_state import KillSwitch, SafeHaltManager, get_system_state
from broker_sakuma.services.system_control_service import SystemControlService, SystemTransitionError


def test_start_moves_to_online(db_session):
    service = SystemControlService(db_session)
    state = service.start(actor="owner")
    assert state == SystemState.ONLINE
    assert get_system_state(db_session) == SystemState.ONLINE


def test_pause_then_resume(db_session):
    service = SystemControlService(db_session)
    service.start(actor="owner")
    assert service.pause(actor="owner") == SystemState.PAUSED
    assert get_system_state(db_session) == SystemState.PAUSED
    assert service.resume(actor="owner") == SystemState.ONLINE


def test_kill_switch_is_reachable_from_any_state(db_session):
    service = SystemControlService(db_session)
    service.start(actor="owner")
    service.pause(actor="owner")

    state = service.engage_kill_switch(actor="owner", reason="suspicious activity")
    assert state == SystemState.EMERGENCY_STOP
    assert get_system_state(db_session) == SystemState.EMERGENCY_STOP


def test_kill_switch_engage_is_idempotent(db_session):
    service = SystemControlService(db_session)
    service.engage_kill_switch(actor="owner", reason="first")
    service.engage_kill_switch(actor="owner", reason="second")

    from broker_sakuma.db import models

    events = db_session.query(models.SystemEvent).filter_by(event_type="KILL_SWITCH_ENGAGED").all()
    assert len(events) == 1  # second call was a no-op, not a duplicate alert


def test_resume_cannot_clear_emergency_stop(db_session):
    service = SystemControlService(db_session)
    KillSwitch(db_session).engage(reason="test", actor="owner")

    with pytest.raises(SystemTransitionError) as exc_info:
        service.resume(actor="owner")
    assert exc_info.value.current_state == SystemState.EMERGENCY_STOP


def test_pause_cannot_override_safe_halt(db_session):
    service = SystemControlService(db_session)
    SafeHaltManager(db_session).halt(category="CUSTODY_FAILURE", reason="test", actor="system")

    with pytest.raises(SystemTransitionError) as exc_info:
        service.pause(actor="owner")
    assert exc_info.value.current_state == SystemState.SAFE_HALT


def test_start_cannot_override_emergency_stop(db_session):
    service = SystemControlService(db_session)
    KillSwitch(db_session).engage(reason="test", actor="owner")

    with pytest.raises(SystemTransitionError):
        service.start(actor="owner")
