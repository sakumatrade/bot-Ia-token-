"""Backs the `/api/system/{start,pause,resume,kill-switch}` endpoints
(spec section 38). A thin, testable state machine on top of
``KillSwitch``/``get_system_state`` — the HTTP layer only handles auth and
status-code mapping.

Deliberately not exposed here: clearing EMERGENCY_STOP or SAFE_HALT.
"Bots em Kill Switch não podem reiniciar sozinhos" (spec section 29) — a
generic /resume must never be the thing that clears an emergency stop.
That needs its own, more heavily authorized flow, not built yet.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from broker_sakuma.core.enums import SystemState
from broker_sakuma.db import models
from broker_sakuma.engines.system_state import KillSwitch, get_system_state


class SystemTransitionError(Exception):
    def __init__(self, message: str, current_state: SystemState):
        super().__init__(message)
        self.current_state = current_state


class SystemControlService:
    def __init__(self, session: Session):
        self.session = session
        self.kill_switch = KillSwitch(session)

    def start(self, actor: str) -> SystemState:
        return self._to_online(actor, event_type="SYSTEM_START")

    def resume(self, actor: str) -> SystemState:
        return self._to_online(actor, event_type="SYSTEM_RESUME")

    def _to_online(self, actor: str, event_type: str) -> SystemState:
        current = get_system_state(self.session)
        if current in (SystemState.EMERGENCY_STOP, SystemState.SAFE_HALT):
            raise SystemTransitionError(
                f"cannot move to ONLINE from {current.value}; it must be cleared explicitly first",
                current_state=current,
            )
        self._record(event_type, SystemState.ONLINE, actor, reason=f"{event_type.lower()} requested")
        return SystemState.ONLINE

    def pause(self, actor: str) -> SystemState:
        current = get_system_state(self.session)
        if current in (SystemState.EMERGENCY_STOP, SystemState.SAFE_HALT):
            raise SystemTransitionError(
                f"cannot pause from {current.value}; it must be cleared explicitly first",
                current_state=current,
            )
        self._record("SYSTEM_PAUSE", SystemState.PAUSED, actor, reason="pause requested")
        return SystemState.PAUSED

    def engage_kill_switch(self, actor: str, reason: str) -> SystemState:
        if self.kill_switch.is_engaged():
            return SystemState.EMERGENCY_STOP  # idempotent: pressing it twice is safe, not a duplicate alert
        self.kill_switch.engage(reason=reason, actor=actor)
        return SystemState.EMERGENCY_STOP

    def _record(self, event_type: str, state: SystemState, actor: str, reason: str) -> None:
        self.session.add(models.SystemEvent(event_type=event_type, state=state, reason=reason, actor=actor))
        self.session.commit()
