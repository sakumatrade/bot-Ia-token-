"""TradeSuggestionEngine (spec sections 33, 61): the honest version of
"let me approve every trade myself before it happens." It never executes
anything — there is no signer in this codebase (`engines/signer.py`) and
none will be built, human-approved or not, because the missing piece was
never "who clicks the button," it's that this codebase has no tested,
audited way to safely custody or move real funds at all.

What this *can* do honestly: reuse the same triage (`PumpFunMonitor`)
and learned confidence (`PatternLearner`) every other phase already
built, and turn a promising WATCH decision into a plain-language
suggestion tied to one of the user's own registered watch-only wallets.
Sizing the position is left entirely to whoever reads it — nothing here
suggests a dollar amount — and acting on it, if ever, means doing so
manually in the user's own wallet software (Phantom, Jupiter, etc.),
completely outside this system.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import TradeSide, TradeSuggestionStatus, WalletKind
from broker_sakuma.db import models
from broker_sakuma.engines.pattern_learning import PatternLearner, liquidity_bucket_tag


class TradeSuggestionEngine:
    def __init__(self, session: Session):
        self.session = session
        self.learner = PatternLearner(session)

    def _active_watch_only_wallet(self) -> models.Wallet | None:
        stmt = select(models.Wallet).where(models.Wallet.kind == WalletKind.WATCH_ONLY, models.Wallet.is_active.is_(True))
        return self.session.execute(stmt).scalars().first()

    def suggest_from_decision(self, decision) -> models.TradeSuggestion | None:
        """Given a PumpFunMonitor PipelineDecision, propose a suggestion
        if it's actionable (WATCH) and the user has a wallet registered to
        point it at. Returns None otherwise — never fabricates a
        suggestion with nowhere for it to go.
        """

        if decision.action != "WATCH":
            return None

        wallet = self._active_watch_only_wallet()
        if wallet is None:
            return None

        liquidity_usd = decision.liquidity_analysis.liquidity_usd
        multiplier = self.learner.confidence_multiplier(liquidity_usd)
        bucket = liquidity_bucket_tag(liquidity_usd)

        if multiplier == 1.0:
            confidence_note = "ainda sem histórico suficiente para essa faixa de liquidez"
        elif multiplier > 1.0:
            confidence_note = f"resultados simulados passados nessa faixa de liquidez ({bucket}) foram positivos"
        else:
            confidence_note = f"resultados simulados passados nessa faixa de liquidez ({bucket}) foram negativos"

        reasoning = (
            f"{decision.launch.symbol} ({decision.launch.name}): passou no filtro inicial de risco "
            f"(liquidez ${liquidity_usd:.2f}, score de risco {decision.risk_analysis.risk_score:.0f}/100). "
            f"{confidence_note}. Isto é apenas uma sugestão baseada em simulação — nenhuma operação real "
            f"foi feita, e o valor a arriscar (se algum) é decisão sua."
        )

        suggestion = models.TradeSuggestion(
            wallet_id=wallet.id,
            token_id=decision.token_id,
            side=TradeSide.BUY,
            reasoning=reasoning,
            risk_score=decision.risk_analysis.risk_score,
            status=TradeSuggestionStatus.PENDING,
        )
        self.session.add(suggestion)
        self.session.commit()
        return suggestion

    def set_status(self, suggestion: models.TradeSuggestion, status: TradeSuggestionStatus) -> models.TradeSuggestion:
        suggestion.status = status
        self.session.add(suggestion)
        self.session.commit()
        return suggestion
