"""WalletManager (spec sections 32, 34): all wallet metadata CRUD the GUI
needs, with zero secret material ever touching this layer.

Changing a Receiving Wallet's address requires ``extra_authorization=True``
(spec section 34: "Receiving Wallet deve exigir autenticação para
alteração") — the caller (the API layer, once wired to a real
authorization check beyond the base API key) is responsible for only
passing that flag after a genuine additional check, not a default.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.core.enums import WalletKind, WalletType
from broker_sakuma.db import models


class DuplicateWalletError(Exception):
    pass


class WalletAuthorizationError(Exception):
    pass


class WalletManager:
    def __init__(self, session: Session):
        self.session = session

    def add_wallet(
        self,
        name: str,
        blockchain: str,
        wallet_type: WalletType,
        kind: WalletKind,
        public_address: str,
        purpose: str | None = None,
        owner_bot_id: str | None = None,
    ) -> models.Wallet:
        if not public_address.strip():
            raise ValueError("public_address cannot be empty")

        existing = self.session.execute(
            select(models.Wallet).where(
                models.Wallet.blockchain == blockchain, models.Wallet.public_address == public_address
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateWalletError(f"a wallet for {blockchain}:{public_address} is already registered")

        wallet = models.Wallet(
            name=name,
            blockchain=blockchain,
            wallet_type=wallet_type,
            kind=kind,
            public_address=public_address,
            purpose=purpose,
            owner_bot_id=owner_bot_id,
            is_active=True,
        )
        self.session.add(wallet)
        self.session.commit()

        self.session.add(
            models.AuditLog(
                actor="wallet_manager",
                action="WALLET_ADDED",
                entity_type="wallet",
                entity_id=wallet.id,
                details={"name": name, "blockchain": blockchain, "wallet_type": wallet_type.value},
            )
        )
        self.session.commit()
        return wallet

    def rename_wallet(self, wallet: models.Wallet, new_name: str) -> models.Wallet:
        if not new_name.strip():
            raise ValueError("new_name cannot be empty")
        wallet.name = new_name
        self.session.add(wallet)
        self.session.commit()
        return wallet

    def set_active(self, wallet: models.Wallet, is_active: bool) -> models.Wallet:
        wallet.is_active = is_active
        self.session.add(wallet)
        self.session.add(
            models.AuditLog(
                actor="wallet_manager",
                action="WALLET_ACTIVATED" if is_active else "WALLET_DEACTIVATED",
                entity_type="wallet",
                entity_id=wallet.id,
                details={},
            )
        )
        self.session.commit()
        return wallet

    def update_address(self, wallet: models.Wallet, new_address: str, extra_authorization: bool = False) -> models.Wallet:
        if not new_address.strip():
            raise ValueError("new_address cannot be empty")

        if WalletType(wallet.wallet_type) == WalletType.RECEIVING_WALLET and not extra_authorization:
            raise WalletAuthorizationError(
                "changing a Receiving Wallet's address requires additional authorization"
            )

        old_address = wallet.public_address
        wallet.public_address = new_address
        self.session.add(wallet)
        self.session.add(
            models.AuditLog(
                actor="wallet_manager",
                action="WALLET_ADDRESS_CHANGED",
                entity_type="wallet",
                entity_id=wallet.id,
                details={"old_address": old_address, "new_address": new_address},
            )
        )
        self.session.commit()
        return wallet

    def list_wallets(self, active_only: bool = False) -> list[models.Wallet]:
        stmt = select(models.Wallet).order_by(models.Wallet.created_at.asc())
        if active_only:
            stmt = stmt.where(models.Wallet.is_active.is_(True))
        return list(self.session.execute(stmt).scalars())
