from __future__ import annotations

import ast
import inspect

import pytest

from broker_sakuma.core.enums import BotState, SystemState, TelegramRole
from broker_sakuma.db import models
from broker_sakuma.engines import telegram_control_service
from broker_sakuma.engines.system_state import get_system_state
from broker_sakuma.engines.telegram_control_service import TelegramControlService


def test_module_never_shells_out_or_evals():
    """Spec section 35: never allow arbitrary OS commands. Enforced by
    asserting the module simply never imports the tools that would let it
    (subprocess, os.system) and never calls eval/exec."""

    tree = ast.parse(inspect.getsource(telegram_control_service))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module.split(".")[0])

    assert "subprocess" not in imported_names
    assert "os" not in imported_names

    call_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "eval" not in call_names
    assert "exec" not in call_names


def make_user(session, telegram_user_id: str, role: TelegramRole | None) -> models.User:
    user = models.User(email=f"{telegram_user_id}@example.com", display_name=telegram_user_id, telegram_user_id=telegram_user_id, telegram_role=role)
    session.add(user)
    session.commit()
    return user


def test_unknown_telegram_user_is_rejected(db_session):
    service = TelegramControlService(db_session)
    result = service.handle_command("999999", "/status")
    assert result.success is False
    assert "autorizado" in result.message


def test_viewer_can_check_status(db_session):
    make_user(db_session, "111", TelegramRole.VIEWER)
    service = TelegramControlService(db_session)
    result = service.handle_command("111", "/status")
    assert result.success is True
    assert "ONLINE" in result.message


def test_viewer_cannot_pause(db_session):
    make_user(db_session, "111", TelegramRole.VIEWER)
    service = TelegramControlService(db_session)
    result = service.handle_command("111", "/pause")
    assert result.success is False
    assert "permissão" in result.message


def test_operator_can_pause_and_resume(db_session):
    make_user(db_session, "222", TelegramRole.OPERATOR)
    service = TelegramControlService(db_session)

    result = service.handle_command("222", "/pause")
    assert result.success is True
    assert get_system_state(db_session) == SystemState.PAUSED

    result = service.handle_command("222", "/resume")
    assert result.success is True
    assert get_system_state(db_session) == SystemState.ONLINE


def test_operator_cannot_kill(db_session):
    make_user(db_session, "222", TelegramRole.OPERATOR)
    service = TelegramControlService(db_session)
    result = service.handle_command("222", "/kill")
    assert result.success is False
    assert "permissão" in result.message


def test_owner_kill_requires_confirmation(db_session):
    make_user(db_session, "333", TelegramRole.OWNER)
    service = TelegramControlService(db_session)

    result = service.handle_command("333", "/kill")
    assert result.success is False
    assert result.requires_confirmation is True
    assert get_system_state(db_session) == SystemState.ONLINE  # not engaged yet


def test_owner_kill_requires_a_reason_even_when_confirmed(db_session):
    make_user(db_session, "333", TelegramRole.OWNER)
    service = TelegramControlService(db_session)

    result = service.handle_command("333", "/kill", args=["CONFIRM"])
    assert result.success is False
    assert get_system_state(db_session) == SystemState.ONLINE


def test_owner_kill_confirmed_with_reason_engages(db_session):
    make_user(db_session, "333", TelegramRole.OWNER)
    service = TelegramControlService(db_session)

    result = service.handle_command("333", "/kill", args=["CONFIRM", "suspicious", "wallet", "activity"])
    assert result.success is True
    assert get_system_state(db_session) == SystemState.EMERGENCY_STOP


def test_every_attempt_is_audit_logged(db_session):
    make_user(db_session, "111", TelegramRole.VIEWER)
    service = TelegramControlService(db_session)

    service.handle_command("111", "/status")  # authorized
    service.handle_command("111", "/pause")  # unauthorized (wrong role)
    service.handle_command("999", "/status")  # unauthorized (unknown user)

    logs = db_session.query(models.AuditLog).filter(models.AuditLog.action.like("TELEGRAM_COMMAND:%")).all()
    assert len(logs) == 3
    assert all(log.details.get("system_state") is not None for log in logs)


def test_unknown_command_is_rejected_and_logged(db_session):
    make_user(db_session, "111", TelegramRole.VIEWER)
    service = TelegramControlService(db_session)
    result = service.handle_command("111", "/not_a_real_command")
    assert result.success is False

    logs = db_session.query(models.AuditLog).filter_by(action="TELEGRAM_COMMAND:not_a_real_command").all()
    assert len(logs) == 1


def test_deaths_report_reflects_real_data(db_session):
    make_user(db_session, "111", TelegramRole.VIEWER)
    db_session.add_all([
        models.Bot(name="Son 500", state=BotState.DEAD),
        models.Bot(name="Son 501", state=BotState.ACTIVE),
    ])
    db_session.commit()

    service = TelegramControlService(db_session)
    result = service.handle_command("111", "/deaths")
    assert "1" in result.message


def test_daily_report_contains_all_spec_fields(db_session):
    make_user(db_session, "111", TelegramRole.VIEWER)
    service = TelegramControlService(db_session)
    result = service.handle_command("111", "/daily")

    for field in [
        "Mother Capital",
        "Operational Capital",
        "Reserve",
        "Daily Result",
        "Total Result",
        "Active Bots",
        "Dead Bots",
        "Resurrections",
        "New Strategies",
        "New Theses",
        "Capital Loaned",
        "Interest",
        "Research",
        "Alerts",
        "System Status",
    ]:
        assert field in result.message
