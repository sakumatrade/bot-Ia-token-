from __future__ import annotations

import pytest

from broker_sakuma.core.enums import WalletKind, WalletType
from broker_sakuma.engines.wallet_manager import DuplicateWalletError, WalletAuthorizationError, WalletManager


def test_add_wallet(db_session):
    manager = WalletManager(db_session)
    wallet = manager.add_wallet(
        name="Mother Wallet",
        blockchain="solana",
        wallet_type=WalletType.MOTHER_WALLET,
        kind=WalletKind.WATCH_ONLY,
        public_address="Addr1",
    )
    assert wallet.is_active is True
    assert wallet.kind == WalletKind.WATCH_ONLY


def test_duplicate_address_on_same_blockchain_is_rejected(db_session):
    manager = WalletManager(db_session)
    manager.add_wallet(
        name="A", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
    )
    with pytest.raises(DuplicateWalletError):
        manager.add_wallet(
            name="B", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
        )


def test_same_address_on_different_blockchain_is_allowed(db_session):
    manager = WalletManager(db_session)
    manager.add_wallet(
        name="A", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
    )
    # different blockchain namespace, same literal address string — allowed
    wallet = manager.add_wallet(
        name="B", blockchain="ethereum", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
    )
    assert wallet.blockchain == "ethereum"


def test_rename_wallet(db_session):
    manager = WalletManager(db_session)
    wallet = manager.add_wallet(
        name="Old Name", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
    )
    manager.rename_wallet(wallet, "New Name")
    assert wallet.name == "New Name"


def test_activate_and_deactivate(db_session):
    manager = WalletManager(db_session)
    wallet = manager.add_wallet(
        name="A", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
    )
    manager.set_active(wallet, False)
    assert wallet.is_active is False
    manager.set_active(wallet, True)
    assert wallet.is_active is True


def test_receiving_wallet_address_change_requires_extra_authorization(db_session):
    manager = WalletManager(db_session)
    wallet = manager.add_wallet(
        name="Receiving",
        blockchain="solana",
        wallet_type=WalletType.RECEIVING_WALLET,
        kind=WalletKind.WATCH_ONLY,
        public_address="Addr1",
    )

    with pytest.raises(WalletAuthorizationError):
        manager.update_address(wallet, "Addr2", extra_authorization=False)

    manager.update_address(wallet, "Addr2", extra_authorization=True)
    assert wallet.public_address == "Addr2"


def test_non_receiving_wallet_address_change_does_not_require_extra_authorization(db_session):
    manager = WalletManager(db_session)
    wallet = manager.add_wallet(
        name="Bot Wallet",
        blockchain="solana",
        wallet_type=WalletType.BOT_WALLET,
        kind=WalletKind.SIGNING,
        public_address="Addr1",
    )
    manager.update_address(wallet, "Addr2", extra_authorization=False)
    assert wallet.public_address == "Addr2"


def test_list_wallets_active_only(db_session):
    manager = WalletManager(db_session)
    active = manager.add_wallet(
        name="Active", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr1"
    )
    inactive = manager.add_wallet(
        name="Inactive", blockchain="solana", wallet_type=WalletType.BOT_WALLET, kind=WalletKind.SIGNING, public_address="Addr2"
    )
    manager.set_active(inactive, False)

    all_wallets = manager.list_wallets(active_only=False)
    active_wallets = manager.list_wallets(active_only=True)

    assert len(all_wallets) == 2
    assert [w.id for w in active_wallets] == [active.id]
