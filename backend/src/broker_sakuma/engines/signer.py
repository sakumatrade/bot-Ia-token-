"""Signer abstraction (spec section 33).

No private key, seed phrase, or mnemonic is ever handled by this Python
backend — there is no field for one anywhere in ``db.models.Wallet`` (see
``tests/test_wallet_model_never_stores_secrets.py``), and there never will
be. Real signing for a ``SIGNING``-kind wallet has to happen on the macOS
side, backed by the Keychain (Security framework), which this Linux
backend has no access to at all.

``Signer`` is the interface that boundary is built around. A
``WATCH_ONLY`` wallet gets a ``WatchOnlySigner`` that structurally cannot
sign anything. A ``SIGNING`` wallet has no working signer *in this
backend* — asking for one raises ``SignerNotAvailableError`` rather than
pretending to sign, which would be exactly the "simular uma integração
real como se fosse funcional" the spec forbids (section 61). The real
signer for a SIGNING wallet is a future macOS-side component (backed by
the Keychain), reached over the Local API once live execution exists —
not built yet, because live trading itself is still disabled.
"""

from __future__ import annotations

from typing import Protocol

from broker_sakuma.core.enums import WalletKind
from broker_sakuma.db import models


class SigningNotPermittedError(Exception):
    """Raised when asking a watch-only wallet's signer to sign anything."""


class SignerNotAvailableError(Exception):
    """Raised for a SIGNING wallet: this backend has no real signer. The
    real one lives on the macOS side, backed by the Keychain."""


class Signer(Protocol):
    def sign_transaction(self, transaction_bytes: bytes) -> bytes: ...


class WatchOnlySigner:
    """The only Signer this backend can actually construct. It exists so
    "attempt to sign with a watch-only wallet" is a normal, testable error
    path rather than an AttributeError or a silent no-op.
    """

    def __init__(self, wallet: models.Wallet):
        self.wallet = wallet

    def sign_transaction(self, transaction_bytes: bytes) -> bytes:
        raise SigningNotPermittedError(
            f"wallet {self.wallet.id} ({self.wallet.name}) is WATCH_ONLY and cannot sign transactions"
        )


def get_signer(wallet: models.Wallet) -> WatchOnlySigner:
    kind = WalletKind(wallet.kind)
    if kind == WalletKind.WATCH_ONLY:
        return WatchOnlySigner(wallet)
    raise SignerNotAvailableError(
        f"wallet {wallet.id} ({wallet.name}) is a SIGNING wallet; this backend has no Keychain access — "
        "signing must be performed by the macOS app"
    )
