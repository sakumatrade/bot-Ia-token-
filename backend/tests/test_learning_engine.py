from __future__ import annotations

import ast
import inspect

import pytest

from broker_sakuma.config import ThesisPolicyConfig
from broker_sakuma.core.enums import BotState, InfoClassification, ThesisState
from broker_sakuma.db import models
from broker_sakuma.engines import learning_engine
from broker_sakuma.engines.learning_engine import LearningEngine
from broker_sakuma.engines.thesis_engine import ThesisEngine


def test_learning_engine_has_no_access_to_safety_controls():
    """Spec section 26/7: Learning must never be able to touch Kill Switch,
    risk limits, custody, transfer limits, or security policy. Enforced
    here by asserting the module simply never imports or names those
    symbols — there is no code path to reach for.
    """

    tree = ast.parse(inspect.getsource(learning_engine))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)

    forbidden_symbols = {
        "KillSwitch",
        "SafeHaltManager",
        "RiskPolicyConfig",
        "RiskEngine",
        "Transfer",
        "Wallet",
        "Settings",
    }
    violations = imported_names & forbidden_symbols
    assert not violations, f"LearningEngine module must never import {violations}"

    # Belt and suspenders: it must never construct or mutate live-trading state either.
    call_and_attr_source = "\n".join(
        line for line in inspect.getsource(learning_engine).splitlines() if not line.strip().startswith("#")
    )
    assert "live_trading_enabled = True" not in call_and_attr_source
    assert ".engage(" not in call_and_attr_source


@pytest.fixture()
def bot(db_session):
    b = models.Bot(name="Son 090", state=BotState.ACTIVE)
    db_session.add(b)
    db_session.commit()
    return b


def test_hypothesis_is_classified_distinctly_from_fact(db_session, bot):
    engine = LearningEngine(db_session)
    fact = engine.record_fact(bot.id, "Pump.fun launches spike on weekends")
    hypothesis = engine.propose_hypothesis(bot.id, "Weekend spikes correlate with lower liquidity")

    assert fact.kind == InfoClassification.FACT
    assert hypothesis.kind == InfoClassification.HYPOTHESIS


def test_compare_strategies_is_pure_and_has_no_side_effects(db_session):
    engine = LearningEngine(db_session)
    result = engine.compare_strategies({"return_pct": 0.10}, {"return_pct": 0.05})
    assert result["better"] == "a"

    count_before = db_session.query(models.LearningEvent).count()
    engine.compare_strategies({"return_pct": 0.01}, {"return_pct": 0.20})
    count_after = db_session.query(models.LearningEvent).count()
    assert count_before == count_after  # comparison never writes anything


def test_propose_new_test_requires_thesis_engine(db_session, bot):
    engine = LearningEngine(db_session)  # no thesis_engine wired in
    with pytest.raises(RuntimeError):
        engine.propose_new_test(bot, "New idea", "some hypothesis")


def test_propose_new_test_creates_thesis_that_still_starts_at_five_dollars(db_session, bot):
    thesis_engine = ThesisEngine(db_session, ThesisPolicyConfig())
    engine = LearningEngine(db_session, thesis_engine=thesis_engine)

    thesis = engine.propose_new_test(bot, "New idea", "creators with prior successful launches perform better")
    assert thesis.state == ThesisState.RESEARCH

    thesis_engine.advance_to_backtest(thesis)
    thesis_engine.advance_to_paper(thesis)
    thesis_engine.start_initial_test(thesis, bot)
    assert thesis.current_capital_usd == 5.0

    hypothesis_event = (
        db_session.query(models.LearningEvent)
        .filter_by(source_bot_id=bot.id, kind=InfoClassification.HYPOTHESIS)
        .one()
    )
    assert hypothesis_event.title == "New idea"
