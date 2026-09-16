from __future__ import annotations

import pytest

from broker_sakuma.core.enums import WalletKind, WalletType
from broker_sakuma.db import models
from broker_sakuma.engines.signer import (
    SignerNotAvailableError,
    SigningNotPermittedError,
    WatchOnlySigner,
    get_signer,
)


def test_watch_only_wallet_gets_a_watch_only_signer(db_session):
    wallet = models.Wallet(
        name="Mother Watch",
        wallet_type=WalletType.MOTHER_WALLET,
        kind=WalletKind.WATCH_ONLY,
        public_address="Addr1",
    )
    db_session.add(wallet)
    db_session.commit()

    signer = get_signer(wallet)
    assert isinstance(signer, WatchOnlySigner)


def test_watch_only_signer_refuses_to_sign(db_session):
    wallet = models.Wallet(
        name="Mother Watch",
        wallet_type=WalletType.MOTHER_WALLET,
        kind=WalletKind.WATCH_ONLY,
        public_address="Addr1",
    )
    db_session.add(wallet)
    db_session.commit()

    signer = get_signer(wallet)
    with pytest.raises(SigningNotPermittedError):
        signer.sign_transaction(b"fake-tx-bytes")


def test_signing_wallet_has_no_real_signer_in_this_backend(db_session):
    wallet = models.Wallet(
        name="Bot Signer",
        wallet_type=WalletType.BOT_WALLET,
        kind=WalletKind.SIGNING,
        public_address="Addr2",
    )
    db_session.add(wallet)
    db_session.commit()

    with pytest.raises(SignerNotAvailableError):
        get_signer(wallet)
