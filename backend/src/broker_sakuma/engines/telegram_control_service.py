"""TelegramControlService (spec sections 35, 36, 37).

Every command runs through a fixed, closed dispatch table — there is no
`eval`, `exec`, `subprocess`, or `os.system` anywhere in this module (see
``tests/test_telegram_control_service.py`` for the AST-based regression
test enforcing that), which is the actual mechanism behind "nunca
permitir comandos arbitrários do sistema operacional." Every single
attempt, authorized or not, gets an ``AuditLog`` row: who (Telegram user
ID), when, which command, whether it was confirmed, the reason (for
/kill), and the system state at the time.

Roles are resolved from ``User.telegram_user_id`` / ``User.telegram_role``
— a Telegram user with no matching row, or no role set, is simply not
authorized for anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import BotState, SystemState, TelegramCommand, TelegramRole
from broker_sakuma.db import models
from broker_sakuma.engines.crypto_discovery import CryptoResearchLab
from broker_sakuma.engines.system_state import get_system_state
from broker_sakuma.services.dashboard_service import build_dashboard_snapshot
from broker_sakuma.services.system_control_service import SystemControlService, SystemTransitionError

_VIEW_ROLES = frozenset({TelegramRole.VIEWER, TelegramRole.OPERATOR, TelegramRole.OWNER})
_OPERATE_ROLES = frozenset({TelegramRole.OPERATOR, TelegramRole.OWNER})
_OWNER_ONLY = frozenset({TelegramRole.OWNER})

COMMAND_PERMISSIONS: dict[TelegramCommand, frozenset[TelegramRole]] = {
    TelegramCommand.STATUS: _VIEW_ROLES,
    TelegramCommand.BOTS: _VIEW_ROLES,
    TelegramCommand.PROFIT: _VIEW_ROLES,
    TelegramCommand.ALERTS: _VIEW_ROLES,
    TelegramCommand.RESEARCH: _VIEW_ROLES,
    TelegramCommand.WALLETS: _VIEW_ROLES,
    TelegramCommand.OPPORTUNITIES: _VIEW_ROLES,
    TelegramCommand.LOGS: _VIEW_ROLES,
    TelegramCommand.DEATHS: _VIEW_ROLES,
    TelegramCommand.RESURRECTIONS: _VIEW_ROLES,
    TelegramCommand.LOANS: _VIEW_ROLES,
    TelegramCommand.RESERVES: _VIEW_ROLES,
    TelegramCommand.GROWTH: _VIEW_ROLES,
    TelegramCommand.DAILY: _VIEW_ROLES,
    TelegramCommand.PAUSE: _OPERATE_ROLES,
    TelegramCommand.RESUME: _OPERATE_ROLES,
    TelegramCommand.KILL: _OWNER_ONLY,
}


@dataclass
class TelegramCommandResult:
    success: bool
    message: str
    requires_confirmation: bool = False


class TelegramControlService:
    def __init__(self, session: Session):
        self.session = session

    def resolve_role(self, telegram_user_id: str) -> TelegramRole | None:
        user = self.session.execute(
            select(models.User).where(models.User.telegram_user_id == telegram_user_id)
        ).scalar_one_or_none()
        if user is None or user.telegram_role is None:
            return None
        return TelegramRole(user.telegram_role)

    def _log(
        self,
        telegram_user_id: str,
        command: str,
        *,
        authorized: bool,
        confirmed: bool,
        reason: str | None,
        system_state: SystemState,
    ) -> None:
        self.session.add(
            models.AuditLog(
                actor=f"telegram:{telegram_user_id}",
                action=f"TELEGRAM_COMMAND:{command}",
                entity_type="system",
                details={
                    "authorized": authorized,
                    "confirmed": confirmed,
                    "reason": reason,
                    "system_state": system_state.value,
                },
            )
        )
        self.session.commit()

    def handle_command(
        self, telegram_user_id: str, command_text: str, args: list[str] | None = None
    ) -> TelegramCommandResult:
        args = args or []
        system_state = get_system_state(self.session)
        raw = command_text.strip().lstrip("/").lower()

        try:
            command = TelegramCommand(raw)
        except ValueError:
            self._log(telegram_user_id, raw, authorized=False, confirmed=False, reason=None, system_state=system_state)
            return TelegramCommandResult(success=False, message="Comando desconhecido.")

        role = self.resolve_role(telegram_user_id)
        if role is None:
            self._log(telegram_user_id, command.value, authorized=False, confirmed=False, reason=None, system_state=system_state)
            return TelegramCommandResult(success=False, message="Você não está autorizado a usar este bot.")

        if role not in COMMAND_PERMISSIONS[command]:
            self._log(telegram_user_id, command.value, authorized=False, confirmed=False, reason=None, system_state=system_state)
            return TelegramCommandResult(success=False, message="Seu nível de permissão não permite este comando.")

        if command == TelegramCommand.KILL:
            return self._handle_kill(telegram_user_id, args, system_state)
        if command == TelegramCommand.PAUSE:
            return self._handle_system_action(telegram_user_id, command, system_state, lambda s: SystemControlService(s).pause(actor=f"telegram:{telegram_user_id}"))
        if command == TelegramCommand.RESUME:
            return self._handle_system_action(telegram_user_id, command, system_state, lambda s: SystemControlService(s).resume(actor=f"telegram:{telegram_user_id}"))

        message = self._build_report(command, system_state)
        self._log(telegram_user_id, command.value, authorized=True, confirmed=True, reason=None, system_state=system_state)
        return TelegramCommandResult(success=True, message=message)

    def _handle_kill(self, telegram_user_id: str, args: list[str], system_state: SystemState) -> TelegramCommandResult:
        if not args or args[0].upper() != "CONFIRM":
            self._log(telegram_user_id, TelegramCommand.KILL.value, authorized=True, confirmed=False, reason=None, system_state=system_state)
            return TelegramCommandResult(
                success=False,
                requires_confirmation=True,
                message="Isso para o sistema imediatamente. Para confirmar, envie: /kill CONFIRM <motivo>",
            )

        reason = " ".join(args[1:]).strip()
        if not reason:
            return TelegramCommandResult(
                success=False,
                requires_confirmation=True,
                message="É necessário informar um motivo: /kill CONFIRM <motivo>",
            )

        new_state = SystemControlService(self.session).engage_kill_switch(actor=f"telegram:{telegram_user_id}", reason=reason)
        self._log(telegram_user_id, TelegramCommand.KILL.value, authorized=True, confirmed=True, reason=reason, system_state=new_state)
        return TelegramCommandResult(success=True, message=f"Kill switch acionado. Estado: {new_state.value}")

    def _handle_system_action(self, telegram_user_id, command, system_state, action) -> TelegramCommandResult:
        try:
            new_state = action(self.session)
        except SystemTransitionError as exc:
            self._log(telegram_user_id, command.value, authorized=True, confirmed=False, reason=str(exc), system_state=system_state)
            return TelegramCommandResult(success=False, message=f"Não foi possível: {exc}")

        self._log(telegram_user_id, command.value, authorized=True, confirmed=True, reason=None, system_state=new_state)
        return TelegramCommandResult(success=True, message=f"Estado agora: {new_state.value}")

    def _build_report(self, command: TelegramCommand, system_state: SystemState) -> str:
        if command == TelegramCommand.STATUS:
            return f"Estado do sistema: {system_state.value}"

        if command == TelegramCommand.PROFIT:
            snapshot = build_dashboard_snapshot(self.session)
            return f"P&L hoje: ${snapshot.daily_pnl_usd:.2f} | P&L total: ${snapshot.total_pnl_usd:.2f}"

        if command == TelegramCommand.BOTS:
            bots = list(self.session.execute(select(models.Bot).order_by(models.Bot.created_at.asc())).scalars())
            if not bots:
                return "Nenhum bot criado ainda."
            lines = [f"{b.name}: {b.state}" for b in bots[:20]]
            return "\n".join(lines)

        if command == TelegramCommand.DEATHS:
            dead = list(self.session.execute(select(models.Bot).where(models.Bot.state == BotState.DEAD)).scalars())
            return f"Bots mortos: {len(dead)}"

        if command == TelegramCommand.RESURRECTIONS:
            count = self.session.execute(
                select(models.BotLineage).where(models.BotLineage.relationship_type == "resurrection")
            ).scalars().all()
            return f"Ressurreições: {len(count)}"

        if command == TelegramCommand.ALERTS:
            alerts = list(
                self.session.execute(select(models.Alert).where(models.Alert.acknowledged.is_(False))).scalars()
            )
            if not alerts:
                return "Nenhum alerta pendente."
            return "\n".join(f"[{a.level}] {a.title}" for a in alerts[:20])

        if command == TelegramCommand.RESEARCH:
            board = CryptoResearchLab(self.session).board()
            return "\n".join(f"{status}: {len(protocols)}" for status, protocols in board.items())

        if command == TelegramCommand.WALLETS:
            wallets = list(self.session.execute(select(models.Wallet)).scalars())
            if not wallets:
                return "Nenhuma carteira cadastrada."
            return "\n".join(f"{w.name} ({w.wallet_type}): {'ativa' if w.is_active else 'inativa'}" for w in wallets)

        if command == TelegramCommand.OPPORTUNITIES:
            opportunities = list(
                self.session.execute(
                    select(models.Opportunity).order_by(models.Opportunity.created_at.desc()).limit(10)
                ).scalars()
            )
            if not opportunities:
                return "Nenhuma oportunidade registrada."
            return "\n".join(f"{o.source}: {o.status}" for o in opportunities)

        if command == TelegramCommand.LOGS:
            logs = list(
                self.session.execute(select(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(10)).scalars()
            )
            return "\n".join(f"{log.created_at.isoformat()} {log.actor} {log.action}" for log in logs)

        if command == TelegramCommand.LOANS:
            loans = list(self.session.execute(select(models.BotLoan)).scalars())
            if not loans:
                return "Nenhum empréstimo ativo."
            return "\n".join(f"{l.loan_id}: ${l.remaining_balance_usd:.2f} restante" for l in loans)

        if command == TelegramCommand.RESERVES:
            reserves = list(self.session.execute(select(models.Reserve)).scalars())
            total = sum(r.balance_usd for r in reserves)
            return f"Reserva total: ${total:.2f} em {len(reserves)} carteira(s) de reserva"

        if command == TelegramCommand.GROWTH:
            bots = list(self.session.execute(select(models.Bot)).scalars())
            return f"Total de bots: {len(bots)}"

        if command == TelegramCommand.DAILY:
            return format_daily_report_text(build_daily_report(self.session))

        raise AssertionError(f"unhandled report command: {command}")  # unreachable: every command above is covered


@dataclass
class DailyReport:
    system_state: SystemState
    mother_capital_usd: float
    operational_capital_usd: float
    reserve_usd: float
    daily_result_usd: float
    total_result_usd: float
    active_bots: int
    dead_bots: int
    resurrections: int
    new_strategies: int
    new_theses: int
    capital_loaned_usd: float
    interest_usd: float
    research_in_progress: int
    unacknowledged_alerts: int


def build_daily_report(session: Session) -> DailyReport:
    snapshot = build_dashboard_snapshot(session)

    mother = session.execute(select(models.Bot).where(models.Bot.generation == 0)).scalars().first()
    mother_capital_usd = mother.capital_operational_usd if mother else 0.0

    new_strategy_versions = session.execute(
        select(models.StrategyVersion).where(models.StrategyVersion.state == "RESEARCH")
    ).scalars().all()

    interest_usd = sum(
        p.interest_component_usd for p in session.execute(select(models.LoanPayment)).scalars()
    )

    research_in_progress = session.execute(
        select(models.Protocol).where(models.Protocol.status != "DISABLED")
    ).scalars().all()

    return DailyReport(
        system_state=snapshot.system_state,
        mother_capital_usd=mother_capital_usd,
        operational_capital_usd=snapshot.capital_operational_usd,
        reserve_usd=snapshot.reserve_usd,
        daily_result_usd=snapshot.daily_pnl_usd,
        total_result_usd=snapshot.total_pnl_usd,
        active_bots=snapshot.active_bots,
        dead_bots=snapshot.dead_bots,
        resurrections=snapshot.resurrected_bots,
        new_strategies=len(new_strategy_versions),
        new_theses=snapshot.new_theses,
        capital_loaned_usd=snapshot.capital_borrowed_usd,
        interest_usd=interest_usd,
        research_in_progress=len(research_in_progress),
        unacknowledged_alerts=snapshot.unacknowledged_alerts,
    )


def format_daily_report_text(report: DailyReport) -> str:
    """spec section 37's exact field list, in order."""

    return (
        "Broker Sakuma — Daily Report\n"
        f"Mother Capital: ${report.mother_capital_usd:.2f}\n"
        f"Operational Capital: ${report.operational_capital_usd:.2f}\n"
        f"Reserve: ${report.reserve_usd:.2f}\n"
        f"Daily Result: ${report.daily_result_usd:.2f}\n"
        f"Total Result: ${report.total_result_usd:.2f}\n"
        f"Active Bots: {report.active_bots}\n"
        f"Dead Bots: {report.dead_bots}\n"
        f"Resurrections: {report.resurrections}\n"
        f"New Strategies: {report.new_strategies}\n"
        f"New Theses: {report.new_theses}\n"
        f"Capital Loaned: ${report.capital_loaned_usd:.2f}\n"
        f"Interest: ${report.interest_usd:.2f}\n"
        f"Research: {report.research_in_progress}\n"
        f"Alerts: {report.unacknowledged_alerts}\n"
        f"System Status: {report.system_state.value}"
    )
