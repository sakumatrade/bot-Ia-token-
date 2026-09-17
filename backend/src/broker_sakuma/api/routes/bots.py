"""Bot lifecycle endpoints, terminal/curl-friendly (spec sections 7, 8, 10).

``POST /bots/mother`` / ``POST /bots/sons`` / ``POST /bots/{id}/activate``
let a user create a Mother Bot, spawn a Son under it, and "activate" that
Son entirely from a terminal with ``curl`` — no Xcode, no GUI required.

Every dollar involved is a plain float in this backend's own database
(``Bot.capital_operational_usd`` and friends). There is no wallet, private
key, or blockchain call anywhere in this file — "activating" a bot means
running it through the same ThesisEngine + BotLoanEngine machinery every
other phase already uses, which always starts a brand-new thesis at
exactly ``settings.thesis.initial_test_capital_usd`` (spec section 10's
$5 rule), funded via an internal loan from the Mother Bot's own simulated
treasury. See ``docs/ARCHITECTURE.md#security`` for why real money is
structurally out of scope here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, get_settings, require_api_key
from broker_sakuma.api.schemas import ActivateBotResponse, BotSummary, CreateMotherBotRequest, SpawnSonRequest
from broker_sakuma.config import Settings
from broker_sakuma.core.enums import BotLifecycleEventType, BotState
from broker_sakuma.db import models
from broker_sakuma.engines.lineage_engine import GrowthPolicyViolation, LineageEngine
from broker_sakuma.engines.loan_engine import BotLoanEngine, LoanExposureExceeded
from broker_sakuma.engines.thesis_engine import ThesisEngine, ThesisRuleViolation

router = APIRouter(tags=["bots"], dependencies=[Depends(require_api_key)])


@router.get("/bots", response_model=list[BotSummary])
def list_bots(db: Session = Depends(get_db)) -> list[models.Bot]:
    stmt = select(models.Bot).order_by(models.Bot.created_at.asc())
    return list(db.execute(stmt).scalars())


@router.post("/bots/mother", response_model=BotSummary, status_code=status.HTTP_201_CREATED)
def create_mother_bot(
    payload: CreateMotherBotRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> models.Bot:
    existing = db.execute(select(models.Bot).where(models.Bot.generation == 0)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a Mother Bot already exists (id={existing.id}); only one root bot is allowed",
        )

    lineage = LineageEngine(db, settings.growth, settings.max_loss)
    return lineage.create_mother_bot(name=payload.name, initial_capital_usd=payload.initial_capital_usd)


@router.post("/bots/sons", response_model=BotSummary, status_code=status.HTTP_201_CREATED)
def spawn_son(
    payload: SpawnSonRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> models.Bot:
    parent = db.get(models.Bot, payload.parent_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"bot {payload.parent_id} not found")
    if parent.state == BotState.DEAD:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"bot {parent.id} is DEAD; cannot spawn under it")

    lineage = LineageEngine(db, settings.growth, settings.max_loss)
    try:
        return lineage.spawn_son(parent, name=payload.name)
    except GrowthPolicyViolation as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/bots/{bot_id}/activate", response_model=ActivateBotResponse)
def activate_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ActivateBotResponse:
    """Start this bot's first thesis at the fixed $5-rule amount (spec
    section 10) and fund it via an internal loan from its Mother Bot's
    simulated treasury — simulated capital only, never real money."""

    bot = db.get(models.Bot, bot_id)
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"bot {bot_id} not found")
    if bot.state == BotState.DEAD:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"bot {bot_id} is DEAD; cannot activate it")
    if bot.parent_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="a Mother Bot (generation 0) cannot be activated with a thesis"
        )

    mother = db.get(models.Bot, bot.parent_id)
    if mother is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"parent bot {bot.parent_id} not found")

    thesis_engine = ThesisEngine(db, settings.thesis)
    try:
        thesis = thesis_engine.create_thesis(bot)
        thesis_engine.advance_to_backtest(thesis)
        thesis_engine.advance_to_paper(thesis)
        thesis_engine.start_initial_test(thesis, bot)
    except ThesisRuleViolation as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    loan_engine = BotLoanEngine(db, settings.loan)
    try:
        loan_engine.create_loan(
            mother,
            bot,
            principal_usd=thesis.current_capital_usd,
            purpose="$5-rule initial thesis activation",
            thesis_id=thesis.id,
        )
    except LoanExposureExceeded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    bot.state = BotState.ACTIVE
    db.add(bot)
    db.commit()
    db.refresh(bot)

    return ActivateBotResponse(bot=BotSummary.model_validate(bot), thesis_id=thesis.id, initial_capital_usd=thesis.current_capital_usd)


@router.post("/bots/{bot_id}/pause", response_model=BotSummary)
def pause_bot(bot_id: str, db: Session = Depends(get_db)) -> models.Bot:
    """Take this one bot out of the autonomous PAPER-trading loop (spec
    section 64's existing PAUSED state) without touching any other bot —
    the loop only ever picks up bots with ``state == ACTIVE``
    (``engines/autonomous_trading_cycle.py``). Idempotent: pausing an
    already-paused bot just returns it unchanged."""

    bot = db.get(models.Bot, bot_id)
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"bot {bot_id} not found")
    if bot.state == BotState.DEAD:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"bot {bot_id} is DEAD; cannot pause it")
    if bot.state == BotState.PAUSED:
        return bot

    # A bot freshly loaded from the DB comes back with a plain str for
    # this column (no SQLAlchemy Enum type is used), not a BotState
    # instance — BotState(...) normalizes either case.
    previous_state = BotState(bot.state) if bot.state else None
    bot.state = BotState.PAUSED
    db.add(bot)
    db.add(
        models.BotLifecycleEvent(
            bot_id=bot.id,
            event_type=BotLifecycleEventType.STATE_CHANGE,
            from_state=previous_state.value if previous_state else None,
            to_state=BotState.PAUSED.value,
            reason="paused by operator via /api/bots/{id}/pause",
        )
    )
    db.commit()
    db.refresh(bot)
    return bot


@router.post("/bots/{bot_id}/resume", response_model=BotSummary)
def resume_bot(bot_id: str, db: Session = Depends(get_db)) -> models.Bot:
    """Put a PAUSED bot back into ACTIVE so it re-enters the autonomous
    loop. Only valid from PAUSED — this is not a general state-machine
    jump, just the other half of ``/pause``."""

    bot = db.get(models.Bot, bot_id)
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"bot {bot_id} not found")
    if bot.state != BotState.PAUSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"bot {bot_id} is not PAUSED (state={bot.state})")

    bot.state = BotState.ACTIVE
    db.add(bot)
    db.add(
        models.BotLifecycleEvent(
            bot_id=bot.id,
            event_type=BotLifecycleEventType.STATE_CHANGE,
            from_state=BotState.PAUSED.value,
            to_state=BotState.ACTIVE.value,
            reason="resumed by operator via /api/bots/{id}/resume",
        )
    )
    db.commit()
    db.refresh(bot)
    return bot
