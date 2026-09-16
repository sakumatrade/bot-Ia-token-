"""Full integration tests (spec Phase 17): cross-engine scenarios verified
through the real Local API, not isolated unit calls. Each earlier phase
has its own focused tests calling one or two engines directly; these
exercise several engines together and then check the *API's* view of the
result, which is what actually catches a mismatch between what an engine
writes and what a route reads back — exactly how this phase found and
fixed the missing `/api/protocols` endpoint (`CryptoResearchLab` operates
on `Protocol` rows, but no route exposed them until now).
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from broker_sakuma.adapters.pumpfun.mock_provider import MockPumpFunProvider
from broker_sakuma.adapters.pumpfun.monitor import PumpFunMonitor
from broker_sakuma.adapters.pumpfun.provider import LaunchEvent
from broker_sakuma.api.app import create_app
from broker_sakuma.config import (
    GrowthPolicyConfig,
    LoanPolicyConfig,
    MaximumLossPolicyConfig,
    ProtocolRiskScoreConfig,
    RiskPolicyConfig,
    Settings,
    SettlementPolicyConfig,
    ThesisPolicyConfig,
)
from broker_sakuma.core.enums import BotState, InterestModel, SystemState, TelegramRole, TradeSide
from broker_sakuma.db import models
from broker_sakuma.db.base import make_engine, make_session_factory
from broker_sakuma.engines.collective_memory import CollectiveMemoryStore
from broker_sakuma.engines.daily_settlement_engine import DailySettlementEngine
from broker_sakuma.engines.lineage_engine import LineageEngine
from broker_sakuma.engines.loan_engine import BotLoanEngine
from broker_sakuma.engines.max_loss_policy import MaximumLossPolicy
from broker_sakuma.engines.post_mortem_engine import BotPostMortemEngine
from broker_sakuma.engines.protocol_discovery import ProtocolDiscoveryAgent
from broker_sakuma.engines.reserve_growth_engine import ReserveGrowthEngine
from broker_sakuma.engines.resurrection_engine import BotResurrectionEngine
from broker_sakuma.engines.telegram_control_service import TelegramControlService
from broker_sakuma.engines.thesis_engine import ThesisEngine
from broker_sakuma.paper.paper_executor import PaperExecutor, PaperOrderRequest

API_KEY = "integration-test-key"


@pytest.fixture()
def api_settings(tmp_path):
    db_path = tmp_path / "test_integration.db"
    return Settings(database={"url": f"sqlite:///{db_path}"}, local_api={"api_key": API_KEY})


@pytest.fixture()
def client(api_settings):
    return TestClient(create_app(settings=api_settings))


@pytest.fixture()
def auth_headers():
    return {"X-API-Key": API_KEY}


def seed_session(settings):
    engine = make_engine(settings.database.url)
    return make_session_factory(engine)()


def test_full_bot_lifecycle_reflected_correctly_through_the_api(client, auth_headers, api_settings):
    """Mother -> Son -> $5 loan-funded thesis -> paper trade -> DEAD ->
    post-mortem -> resurrection -> new $5 thesis -> daily settlement ->
    reserve growth -> loan repayment, all cross-checked via the real
    Local API responses (not just direct DB/dataclass assertions).
    """

    session = seed_session(api_settings)

    growth_config = GrowthPolicyConfig()
    max_loss_config = MaximumLossPolicyConfig(per_bot_max_loss_usd=5.0)
    lineage = LineageEngine(session, growth_config, max_loss_config)
    mother = lineage.create_mother_bot(initial_capital_usd=1000.0)
    son = lineage.spawn_son(mother, name="Son 900")

    # $5 rule: the thesis records the funding intent...
    thesis_engine = ThesisEngine(session, ThesisPolicyConfig())
    thesis = thesis_engine.create_thesis(son)
    thesis_engine.advance_to_backtest(thesis)
    thesis_engine.advance_to_paper(thesis)
    thesis_engine.start_initial_test(thesis, son)
    assert thesis.current_capital_usd == 5.0

    # ...and the loan engine is what actually moves the $5 into the bot's
    # operational capital, exactly as spec section 17's treasury model
    # intends (Mother lends, at most, an explicitly configured fraction
    # of her own capital).
    loan_engine = BotLoanEngine(session, LoanPolicyConfig(mother_max_total_loan_pct_of_treasury=0.5))
    loan = loan_engine.create_loan(
        mother, son, principal_usd=5.0, purpose="$5 initial thesis test", thesis_id=thesis.id,
        interest_model=InterestModel.PROFIT_SHARE,
    )
    assert son.capital_operational_usd == 5.0

    # A real paper trade through the real RiskEngine-gated executor.
    token = models.Token(mint_address="IntegrationMint1", symbol="INTG")
    session.add(token)
    session.commit()

    risk_config = RiskPolicyConfig(max_position_usd=5.0, min_liquidity_usd=1000.0, min_wallet_balance_usd=0.0)
    executor = PaperExecutor(session, risk_config)
    buy = executor.execute(
        PaperOrderRequest(
            bot_id=son.id, token_id=token.id, side=TradeSide.BUY, reference_price=1.0, quantity=5.0,
            liquidity_usd=5000.0, slippage_pct=0.0, fee_pct=0.0,
        ),
        idempotency_key="integration-buy-1",
    )
    assert buy.approved
    sell = executor.execute(
        PaperOrderRequest(
            bot_id=son.id, token_id=token.id, side=TradeSide.SELL, reference_price=0.5, quantity=5.0,
            liquidity_usd=5000.0, slippage_pct=0.0, fee_pct=0.0,
        ),
        idempotency_key="integration-sell-1",
    )
    assert sell.approved
    assert son.cumulative_pnl_usd == pytest.approx(-2.5)

    # Finish the loss down to the $5 ceiling (the exact per-trade descent
    # to -5.0 is already exhaustively covered by
    # test_paper_executor.py::test_bot_dies_after_repeated_losing_trades;
    # here the point is what happens system-wide once MaximumLossPolicy
    # — the same call PaperExecutor already makes after every fill —
    # actually kills the bot).
    son.cumulative_pnl_usd = -5.0
    session.add(son)
    session.commit()
    died = MaximumLossPolicy().enforce(session, son, reason="thesis lost the full $5 stake")
    assert died is True

    dashboard = client.get("/api/dashboard", headers=auth_headers).json()
    assert dashboard["dead_bots"] == 1
    assert dashboard["active_bots"] == 1  # mother is still active

    bots_response = {b["name"]: b for b in client.get("/api/bots", headers=auth_headers).json()}
    assert bots_response["Son 900"]["state"] == "DEAD"

    trades = client.get("/api/trades", headers=auth_headers).json()
    assert len(trades) == 2

    # Post-mortem + resurrection.
    pm_engine = BotPostMortemEngine(session)
    post_mortem = pm_engine.create_post_mortem(
        son, thesis_id=thesis.id, probable_cause="Sold into a falling market with no stop-loss discipline",
        rule_that_should_have_prevented="max_drawdown_pct risk check",
    )
    resurrection = BotResurrectionEngine(session, lineage, CollectiveMemoryStore(session))
    new_son = resurrection.resurrect(son, post_mortem, correction="Add a drawdown-based exit rule")
    assert new_son.name == "Son 900-R1"

    dashboard = client.get("/api/dashboard", headers=auth_headers).json()
    assert dashboard["resurrected_bots"] == 1

    # The resurrected bot's own first thesis still starts at exactly $5,
    # even though Mother's treasury has ~$995 left.
    new_thesis = thesis_engine.create_thesis(new_son)
    thesis_engine.advance_to_backtest(new_thesis)
    thesis_engine.advance_to_paper(new_thesis)
    thesis_engine.start_initial_test(new_thesis, new_son)
    assert new_thesis.current_capital_usd == 5.0

    # Daily settlement + reserve growth on the resurrected bot, after a
    # (separately, directly credited) profitable day.
    new_son.capital_operational_usd = 20.0
    session.add(new_son)
    session.commit()
    settlement_config = SettlementPolicyConfig(
        operational_capital_retention_pct=0.5, reserve_contribution_pct=0.2, returned_to_mother_pct=0.3
    )
    settlement_engine = DailySettlementEngine(session, settlement_config, ReserveGrowthEngine(session))
    settlement_engine.settle(new_son, date(2026, 9, 16), gross_result_usd=10.0)

    reserves = client.get("/api/reserves", headers=auth_headers).json()
    assert any(r["balance_usd"] == pytest.approx(2.0) for r in reserves)

    # Loan repayment with profit-share interest, verified via /api/loans.
    payment = loan_engine.record_payment(loan, principal_component_usd=5.0, interest_component_usd=0.0)
    assert payment.remaining_balance_usd == 0.0

    loans = client.get("/api/loans", headers=auth_headers).json()
    matching_loan = next(l for l in loans if l["loan_id"] == loan.loan_id)
    assert matching_loan["status"] == "PAID"
    assert matching_loan["remaining_balance_usd"] == 0.0


def test_discovery_to_research_lab_chain_through_the_api(client, auth_headers, api_settings):
    """PumpFunMonitor discovers a launch -> registers a token/creator/
    opportunity; ProtocolDiscoveryAgent separately registers and promotes
    a protocol -- both verified through /api/opportunities and the
    /api/protocols endpoint this phase added.
    """

    session = seed_session(api_settings)

    provider = MockPumpFunProvider([
        LaunchEvent(
            mint_address="DiscoveryMint1", symbol="DISC", name="Discovery Token",
            creator_address="DiscoveryCreator1", initial_liquidity_usd=5000.0,
        )
    ])
    monitor = PumpFunMonitor(session, provider, RiskPolicyConfig(min_liquidity_usd=1000.0))
    decisions = monitor.poll()
    assert decisions[0].action == "WATCH"

    opportunities = client.get("/api/opportunities", headers=auth_headers).json()
    assert any(o["source"] == "pumpfun_monitor" for o in opportunities)

    protocol_agent = ProtocolDiscoveryAgent(session, ProtocolRiskScoreConfig(paper_eligible_max_risk_score=80.0))
    protocol = protocol_agent.register_protocol("Orca", blockchain="solana", category="DEX")
    protocol_agent.update_evidence(protocol, tvl_usd=2_000_000.0, age_days=500, audits=[{"firm": "X"}])
    promoted = protocol_agent.evaluate_for_paper_eligibility(protocol)
    assert promoted is True

    protocols = client.get("/api/protocols", headers=auth_headers).json()
    orca = next(p for p in protocols if p["name"] == "Orca")
    assert orca["status"] == "PAPER_ELIGIBLE"
    assert orca["risk_score"] is not None


def test_telegram_kill_switch_is_consistent_with_api_and_paper_executor(client, auth_headers, api_settings):
    """A kill switch engaged through Telegram must be visible to (and
    enforced by) the API and the paper trading executor — proving all
    three surfaces read the same underlying SystemState, not independent
    copies of it.
    """

    session = seed_session(api_settings)

    owner = models.User(email="owner@example.com", display_name="Owner", telegram_user_id="42", telegram_role=TelegramRole.OWNER)
    session.add(owner)
    session.commit()

    bot = models.Bot(name="Son 910", state=BotState.ACTIVE, capital_operational_usd=50.0)
    token = models.Token(mint_address="KillSwitchMint1", symbol="KS")
    session.add_all([bot, token])
    session.commit()

    telegram = TelegramControlService(session)
    result = telegram.handle_command("42", "/kill", args=["CONFIRM", "suspicious", "wallet", "drain"])
    assert result.success is True

    status_response = client.get("/api/status", headers=auth_headers).json()
    assert status_response["system_state"] == SystemState.EMERGENCY_STOP.value

    resume_response = client.post("/api/system/resume", headers=auth_headers)
    assert resume_response.status_code == 409

    executor = PaperExecutor(session, RiskPolicyConfig())
    trade_result = executor.execute(
        PaperOrderRequest(
            bot_id=bot.id, token_id=token.id, side=TradeSide.BUY, reference_price=1.0, quantity=1.0,
            liquidity_usd=5000.0, slippage_pct=0.0,
        ),
        idempotency_key="post-kill-switch-buy",
    )
    assert not trade_result.approved
    assert "system_state_not_online" in trade_result.reason
