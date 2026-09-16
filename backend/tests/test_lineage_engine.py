from __future__ import annotations

import pytest

from broker_sakuma.config import GrowthPolicyConfig, MaximumLossPolicyConfig
from broker_sakuma.core.enums import BotState
from broker_sakuma.engines.lineage_engine import GrowthPolicyViolation, LineageEngine


@pytest.fixture()
def lineage_engine(db_session):
    return LineageEngine(db_session, GrowthPolicyConfig(), MaximumLossPolicyConfig())


def test_create_mother_bot(lineage_engine):
    mother = lineage_engine.create_mother_bot(initial_capital_usd=1000.0)
    assert mother.generation == 0
    assert mother.parent_id is None
    assert mother.state == BotState.ACTIVE
    assert mother.capital_operational_usd == 1000.0


def test_spawn_son_records_lineage_and_lifecycle(db_session, lineage_engine):
    mother = lineage_engine.create_mother_bot()
    son = lineage_engine.spawn_son(mother, name="Son 001")

    assert son.parent_id == mother.id
    assert son.generation == 1
    assert son.state == BotState.CREATED
    assert son.max_loss_usd == MaximumLossPolicyConfig().per_bot_max_loss_usd

    from broker_sakuma.db import models

    lineage_row = db_session.query(models.BotLineage).filter_by(bot_id=son.id).one()
    assert lineage_row.parent_id == mother.id
    assert lineage_row.relationship_type == "child"


def test_spawn_grandson(lineage_engine):
    mother = lineage_engine.create_mother_bot()
    son = lineage_engine.spawn_son(mother, name="Son 001")
    grandson = lineage_engine.spawn_son(son, name="Son 001-A")

    assert grandson.generation == 2
    assert grandson.parent_id == son.id


def test_max_generations_enforced(db_session):
    engine = LineageEngine(db_session, GrowthPolicyConfig(max_generations=1), MaximumLossPolicyConfig())
    mother = engine.create_mother_bot()
    son = engine.spawn_son(mother, name="Son 001")

    with pytest.raises(GrowthPolicyViolation):
        engine.spawn_son(son, name="Son 001-A")


def test_max_bots_enforced(db_session):
    engine = LineageEngine(db_session, GrowthPolicyConfig(max_bots=2), MaximumLossPolicyConfig())
    mother = engine.create_mother_bot()  # bot #1
    engine.spawn_son(mother, name="Son 001")  # bot #2, hits the cap

    with pytest.raises(GrowthPolicyViolation):
        engine.spawn_son(mother, name="Son 002")


def test_lineage_tree_shape(lineage_engine):
    mother = lineage_engine.create_mother_bot()
    son_a = lineage_engine.spawn_son(mother, name="Son 001")
    lineage_engine.spawn_son(mother, name="Son 002")
    lineage_engine.spawn_son(son_a, name="Son 001-A")

    tree = lineage_engine.lineage_tree(mother.id)
    assert tree["name"] == "Mother Bot"
    assert len(tree["children"]) == 2
    son_a_node = next(c for c in tree["children"] if c["name"] == "Son 001")
    assert len(son_a_node["children"]) == 1
    assert son_a_node["children"][0]["name"] == "Son 001-A"
