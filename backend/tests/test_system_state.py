from __future__ import annotations

import pytest

from broker_sakuma.core.enums import SystemState
from broker_sakuma.engines.system_state import KillSwitch, SafeHaltManager, get_system_state


def test_default_system_state_is_online(db_session):
    assert get_system_state(db_session) == SystemState.ONLINE


def test_kill_switch_engage_and_state(db_session):
    kill_switch = KillSwitch(db_session)
    assert not kill_switch.is_engaged()

    kill_switch.engage(reason="suspicious activity", actor="owner")

    assert kill_switch.is_engaged()
    assert get_system_state(db_session) == SystemState.EMERGENCY_STOP


def test_kill_switch_cannot_reset_itself_without_explicit_call(db_session):
    kill_switch = KillSwitch(db_session)
    kill_switch.engage(reason="test", actor="owner")
    assert kill_switch.is_engaged()

    # Simply re-checking state must never clear it.
    assert kill_switch.is_engaged()
    assert kill_switch.is_engaged()

    kill_switch.reset(reason="confirmed false alarm", actor="owner")
    assert not kill_switch.is_engaged()
    assert get_system_state(db_session) == SystemState.PAUSED


def test_safe_halt_requires_known_category(db_session):
    manager = SafeHaltManager(db_session)
    with pytest.raises(ValueError):
        manager.halt(category="NOT_A_REAL_CATEGORY", reason="x", actor="system")


def test_safe_halt_engages_and_clears(db_session):
    manager = SafeHaltManager(db_session)
    assert not manager.is_halted()

    manager.halt(category="BALANCE_INCONSISTENCY", reason="internal vs observed mismatch", actor="reconciliation")
    assert manager.is_halted()
    assert get_system_state(db_session) == SystemState.SAFE_HALT

    manager.clear(reason="reconciled manually", actor="owner")
    assert not manager.is_halted()
