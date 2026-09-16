"""Global system state (spec section 6), Kill Switch (section 29) and Safe
Halt (section 30).

The system state is derived from the most recent ``SystemEvent`` row rather
than kept as in-memory mutable state, so it survives process restarts and is
naturally auditable. Absence of any event means the system defaults to
``ONLINE`` in simulation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import AlertLevel, SystemState
from broker_sakuma.db import models


def get_system_state(session: Session) -> SystemState:
    stmt = select(models.SystemEvent).order_by(models.SystemEvent.created_at.desc()).limit(1)
    latest = session.execute(stmt).scalar_one_or_none()
    if latest is None:
        return SystemState.ONLINE
    return SystemState(latest.state)


class KillSwitch:
    """Global kill switch. Engaging it blocks every new operation across the
    whole system. A bot or engine may never re-engage itself out of this
    state — only an explicit call from an authorized human action (routed
    through the API layer's authorization, not this class) may reset it.
    """

    def __init__(self, session: Session):
        self.session = session

    def is_engaged(self) -> bool:
        return get_system_state(self.session) == SystemState.EMERGENCY_STOP

    def engage(self, reason: str, actor: str) -> models.SystemEvent:
        event = models.SystemEvent(
            event_type="KILL_SWITCH_ENGAGED",
            state=SystemState.EMERGENCY_STOP,
            reason=reason,
            actor=actor,
        )
        self.session.add(event)
        self.session.add(
            models.AuditLog(
                actor=actor,
                action="KILL_SWITCH_ENGAGED",
                entity_type="system",
                details={"reason": reason},
            )
        )
        self.session.add(
            models.Alert(
                level=AlertLevel.CRITICAL,
                title="Kill Switch Engaged",
                message=reason,
                source="kill_switch",
            )
        )
        self.session.commit()
        return event

    def reset(self, reason: str, actor: str) -> models.SystemEvent:
        """Explicit external reset. Callers must have already enforced that
        ``actor`` is an authorized human (owner-level Telegram/API auth)."""

        event = models.SystemEvent(
            event_type="KILL_SWITCH_RESET",
            state=SystemState.PAUSED,
            reason=reason,
            actor=actor,
        )
        self.session.add(event)
        self.session.add(
            models.AuditLog(
                actor=actor,
                action="KILL_SWITCH_RESET",
                entity_type="system",
                details={"reason": reason},
            )
        )
        self.session.commit()
        return event


class SafeHaltManager:
    """Safe Halt (spec section 30): a critical, non-auto-healable stop.

    Safe Halt is triggered for wallet problems, suspicious transactions,
    security errors, balance inconsistencies, custody failures, critical RPC
    failures, unknown risk, or abnormal behavior. The system never tries to
    auto-fix a financial/security problem; it halts and waits for a human.
    """

    VALID_CATEGORIES = {
        "WALLET_PROBLEM",
        "SUSPICIOUS_TRANSACTION",
        "SECURITY_ERROR",
        "BALANCE_INCONSISTENCY",
        "CUSTODY_FAILURE",
        "CRITICAL_RPC_FAILURE",
        "UNKNOWN_RISK",
        "ABNORMAL_BEHAVIOR",
    }

    def __init__(self, session: Session):
        self.session = session

    def is_halted(self) -> bool:
        return get_system_state(self.session) == SystemState.SAFE_HALT

    def halt(self, category: str, reason: str, actor: str) -> models.SystemEvent:
        if category not in self.VALID_CATEGORIES:
            raise ValueError(f"unknown safe-halt category: {category}")

        event = models.SystemEvent(
            event_type=f"SAFE_HALT:{category}",
            state=SystemState.SAFE_HALT,
            reason=reason,
            actor=actor,
        )
        self.session.add(event)
        self.session.add(
            models.AuditLog(
                actor=actor,
                action="SAFE_HALT",
                entity_type="system",
                details={"category": category, "reason": reason},
            )
        )
        self.session.add(
            models.Alert(
                level=AlertLevel.CRITICAL,
                title=f"Safe Halt: {category}",
                message=reason,
                source="safe_halt",
            )
        )
        self.session.commit()
        return event

    def clear(self, reason: str, actor: str) -> models.SystemEvent:
        """Explicit external clear only — never automatic."""

        event = models.SystemEvent(
            event_type="SAFE_HALT_CLEARED",
            state=SystemState.PAUSED,
            reason=reason,
            actor=actor,
        )
        self.session.add(event)
        self.session.add(
            models.AuditLog(
                actor=actor,
                action="SAFE_HALT_CLEARED",
                entity_type="system",
                details={"reason": reason},
            )
        )
        self.session.commit()
        return event
