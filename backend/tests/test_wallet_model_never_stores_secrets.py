from __future__ import annotations

from broker_sakuma.db import models


def test_wallet_model_has_no_column_for_any_secret_material():
    """Structural guarantee behind spec section 33: no private key, seed
    phrase, mnemonic, or password can ever be stored in this backend's
    database, because there is no column for one — not because application
    code merely chooses not to fill one in.
    """

    column_names = {c.name.lower() for c in models.Wallet.__table__.columns}
    forbidden_substrings = ["private", "secret", "seed", "mnemonic", "password", "passphrase"]

    for column_name in column_names:
        for forbidden in forbidden_substrings:
            assert forbidden not in column_name, f"Wallet.{column_name} looks like it could hold secret material"
