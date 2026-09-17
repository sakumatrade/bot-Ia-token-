"""Growth suggestion endpoints (spec section 63): a nudge that a liquidity
bucket has proven itself with enough real (simulated) round trips, never
an instruction the system acts on. See ``engines/pattern_learning.py``'s
``check_growth_suggestion`` for how these get created — there is no
endpoint here that spawns a bot; "acting on it" means the user clicking
"Criar bot" themselves, exactly like the dashboard's own create-bot card.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, require_api_key
from broker_sakuma.api.schemas import GrowthSuggestionSummary
from broker_sakuma.core.enums import GrowthSuggestionStatus
from broker_sakuma.db import models

router = APIRouter(tags=["growth-suggestions"], dependencies=[Depends(require_api_key)])


@router.get("/growth-suggestions", response_model=list[GrowthSuggestionSummary])
def list_growth_suggestions(
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[models.GrowthSuggestion]:
    stmt = select(models.GrowthSuggestion).order_by(models.GrowthSuggestion.created_at.desc())
    if status_filter:
        try:
            stmt = stmt.where(models.GrowthSuggestion.status == GrowthSuggestionStatus(status_filter))
        except ValueError as exc:
            valid = ", ".join(s.value for s in GrowthSuggestionStatus)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid status {status_filter!r}; must be one of: {valid}",
            ) from exc
    stmt = stmt.offset(offset).limit(limit)
    return list(db.execute(stmt).scalars())


def _update_status(suggestion_id: str, new_status: GrowthSuggestionStatus, db: Session) -> models.GrowthSuggestion:
    suggestion = db.get(models.GrowthSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"growth suggestion {suggestion_id} not found")
    suggestion.status = new_status
    db.commit()
    db.refresh(suggestion)
    return suggestion


@router.post("/growth-suggestions/{suggestion_id}/dismiss", response_model=GrowthSuggestionSummary)
def dismiss_growth_suggestion(suggestion_id: str, db: Session = Depends(get_db)) -> models.GrowthSuggestion:
    return _update_status(suggestion_id, GrowthSuggestionStatus.DISMISSED, db)


@router.post("/growth-suggestions/{suggestion_id}/mark-bot-created", response_model=GrowthSuggestionSummary)
def mark_growth_suggestion_bot_created(suggestion_id: str, db: Session = Depends(get_db)) -> models.GrowthSuggestion:
    """The user already created a bot themselves (via the "Criar bot" card)
    in response to this suggestion — this is just their own tracking; it
    never creates a bot itself."""

    return _update_status(suggestion_id, GrowthSuggestionStatus.BOT_CREATED, db)
